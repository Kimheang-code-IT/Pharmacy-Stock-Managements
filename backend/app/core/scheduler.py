"""In-process scheduler. Runs inside the FastAPI API process — not a Docker service.

Daily expiry-alert scans sleep until the configured UTC hour, then run in this
same process. A short Redis lock keeps a duplicate scan from firing if more
than one API worker is started later. No Celery beat, no extra container.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings

logger = logging.getLogger("stock_pos.scheduler")

LOCK_KEY = "stock_pos:scheduler:expiry_scan"
LOCK_TTL_SECONDS = 3600

BACKUP_LOCK_KEY = "stock_pos:scheduler:backup"
BACKUP_LOCK_TTL_SECONDS = 3600
# How often the backup loop wakes to check whether a run is due. The actual
# cadence is the configured `backup.frequency_hours`.
BACKUP_POLL_SECONDS = 60


def seconds_until_next_scan(now: datetime | None = None) -> float:
    """Seconds until the next daily scan at `expiry_alert_scan_hour` UTC."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    hour = max(0, min(23, int(settings.expiry_alert_scan_hour)))
    target = moment.replace(hour=hour, minute=0, second=0, microsecond=0)
    if moment >= target:
        target += timedelta(days=1)
    return max(1.0, (target - moment).total_seconds())


async def run_expiry_scan_once() -> dict:
    from app.core.database import SessionFactory
    from app.modules.telegram.service import ExpiryAlertService

    async with SessionFactory() as session:
        return await ExpiryAlertService(session).scan_and_send()


async def run_daily_summary_once() -> dict:
    """Telegram daily summary at the configured local time (after the expiry
    scan slot). Never raises into the loop."""
    from app.core.database import SessionFactory
    from app.shared.telegram.service import send_daily_summary

    async with SessionFactory() as session:
        return await send_daily_summary(session)


async def run_audit_archival_once() -> dict:
    """Archive audit rows past `security.audit_retention_days` (never rewrites
    history; moves it to the append-only archive table)."""
    from app.core.database import SessionFactory
    from app.modules.administration import get_setting_value
    from app.shared.audit.service import archive_expired_audit_logs

    async with SessionFactory() as session:
        try:
            retention = int(
                await get_setting_value(session, "security", "audit_retention_days", 365) or 365
            )
        except (TypeError, ValueError):
            retention = 365
        archived = await archive_expired_audit_logs(session, retention_days=retention)
        await session.commit()
        return {"archived": archived, "retention_days": retention}


async def _acquired_scan_lock() -> bool:
    return await _acquired_lock(LOCK_KEY, LOCK_TTL_SECONDS)


async def _acquired_lock(key: str, ttl: int) -> bool:
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        return bool(await redis.set(key, "1", nx=True, ex=ttl))
    except Exception as exc:
        logger.warning("Scheduler lock %s unavailable (%s); running in this process", key, exc)
        return True


async def _release_lock(key: str) -> None:
    try:
        from app.core.redis import get_redis

        await get_redis().delete(key)
    except Exception:  # noqa: BLE001 - best-effort release
        pass


async def run_backup_once(trigger: str = "scheduled") -> dict:
    """Run one Google Sheets backup in its own session/transaction."""
    from app.core.database import SessionFactory
    from app.modules.backup.service import BackupService

    async with SessionFactory() as session:
        job = await BackupService(session).run(trigger=trigger)
        return {
            "id": str(job.id),
            "status": job.status,
            "tables_total": job.tables_total,
            "tables_succeeded": job.tables_succeeded,
            "tables_failed": job.tables_failed,
            "rows_appended": job.rows_appended,
            "rows_updated": job.rows_updated,
        }


async def _backup_due() -> bool:
    """True when automatic backups are enabled, configured, and past due."""
    from app.core.database import SessionFactory
    from app.modules.administration import get_setting_value
    from app.modules.backup.service import ALLOWED_FREQUENCY_HOURS, DEFAULT_FREQUENCY_HOURS

    async with SessionFactory() as session:
        if not await get_setting_value(session, "backup", "enabled", False):
            return False
        sheet_id = str(await get_setting_value(session, "backup", "sheet_id", "") or "").strip()
        secret = str(await get_setting_value(session, "backup", "service_account_json", "") or "").strip()
        if not sheet_id or not secret:
            return False
        try:
            frequency = int(
                await get_setting_value(session, "backup", "frequency_hours", DEFAULT_FREQUENCY_HOURS)
            )
        except (TypeError, ValueError):
            frequency = DEFAULT_FREQUENCY_HOURS
        if frequency not in ALLOWED_FREQUENCY_HOURS:
            frequency = DEFAULT_FREQUENCY_HOURS
        last = str(await get_setting_value(session, "backup", "last_success_at", "") or "").strip()
        if not last:
            return True
        try:
            last_run = datetime.fromisoformat(last)
        except ValueError:
            return True
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= last_run + timedelta(hours=frequency)


async def backup_loop(stop: asyncio.Event) -> None:
    """Wake periodically and run a backup when the configured interval elapsed."""
    logger.info("In-process Google Sheets backup scheduler started")
    while not stop.is_set():
        try:
            if await _backup_due() and await _acquired_lock(BACKUP_LOCK_KEY, BACKUP_LOCK_TTL_SECONDS):
                try:
                    summary = await run_backup_once("scheduled")
                    logger.info("Scheduled backup finished: %s", summary)
                finally:
                    await _release_lock(BACKUP_LOCK_KEY)
        except Exception:
            logger.exception("Scheduled backup failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=BACKUP_POLL_SECONDS)
        except TimeoutError:
            pass


async def _scheduler_supervisor(stop: asyncio.Event) -> None:
    await asyncio.gather(scheduler_loop(stop), backup_loop(stop))


async def scheduler_loop(stop: asyncio.Event) -> None:
    logger.info(
        "In-process scheduler started (expiry scan at %02d:00 UTC)",
        max(0, min(23, int(settings.expiry_alert_scan_hour))),
    )
    while not stop.is_set():
        wait = seconds_until_next_scan()
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            break
        except TimeoutError:
            pass
        if stop.is_set():
            break
        if not await _acquired_scan_lock():
            logger.info("Expiry scan skipped: another API process holds the lock")
            continue
        try:
            summary = await run_expiry_scan_once()
            logger.info("Expiry alert sweep: %s", summary)
        except Exception:
            logger.exception("Expiry alert sweep failed")

        # Daily summary piggybacks on the same daily wake-up slot (after the
        # expiry sweep), gated by its own Settings toggle.
        try:
            summary_result = await run_daily_summary_once()
            if summary_result.get("enabled"):
                logger.info("Telegram daily summary: sent=%s", summary_result.get("sent"))
        except Exception:
            logger.exception("Telegram daily summary failed")

        # Retention: archive audit rows past the configured window.
        try:
            archived = await run_audit_archival_once()
            logger.info("Audit archival: %s", archived)
        except Exception:
            logger.exception("Audit archival failed")


def start_backend_scheduler() -> tuple[asyncio.Event, asyncio.Task[None]]:
    stop = asyncio.Event()
    task = asyncio.create_task(_scheduler_supervisor(stop), name="stock-pos-scheduler")
    return stop, task
