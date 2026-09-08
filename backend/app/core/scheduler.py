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


async def _acquired_scan_lock() -> bool:
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        return bool(await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS))
    except Exception as exc:
        logger.warning("Expiry scan lock unavailable (%s); running in this process", exc)
        return True


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


def start_backend_scheduler() -> tuple[asyncio.Event, asyncio.Task[None]]:
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler_loop(stop), name="stock-pos-scheduler")
    return stop, task
