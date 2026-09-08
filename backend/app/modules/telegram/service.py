"""Product expiry Telegram alerts — spec section 3.6 (use case 2).

The FastAPI API process runs `scan_and_send` daily via `app.core.scheduler`
(in-process; not a Docker Celery beat service). The scan:

- reads the two configurable windows from Settings
  (stock.expiry_alert_1_days / stock.expiry_alert_2_days) and the
  telegram.expiry_alerts_enabled toggle;
- finds expiry-tracked lots (product + batch + expiry date) with remaining
  quantity > 0, derived from immutable stock movements;
- for each lot where days_until_expiry <= alert_N_days and no state row exists
  for that level, sends one Telegram message to every active user with a
  verified telegram_chat_id, then persists the state row.

Alert levels are independent: each fires at most once per lot/level. State
rows are only recorded when at least one recipient actually received the
message, so a failed/missing Telegram configuration retries on the next scan.
No stock mutation ever happens in this job.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.service import get_setting_value
from app.modules.auth.models import User
from app.modules.telegram.models import TelegramExpiryAlertState
from app.modules.telegram.repository import ExpiryAlertRepository

logger = logging.getLogger("stock_pos.telegram")

ALERT_LEVEL_1 = TelegramExpiryAlertState.ALERT_LEVEL_1
ALERT_LEVEL_2 = TelegramExpiryAlertState.ALERT_LEVEL_2

DEFAULT_ALERT_1_DAYS = 90
DEFAULT_ALERT_2_DAYS = 7

Sender = Callable[[str, str], Awaitable[bool]]

ALERT_LEVEL_LABELS = {ALERT_LEVEL_1: "Alert 1 (early warning)", ALERT_LEVEL_2: "Alert 2 (final window)"}


def format_expiry_alert_text(lot: dict, *, alert_level: int, days_until_expiry: int) -> str:
    """Plain-text alert: product name, SKU/barcode, batch, expiry, qty, level."""
    lines = [
        "Stock & POS — Product Expiry Alert",
        f"Level: {ALERT_LEVEL_LABELS.get(alert_level, f'Alert {alert_level}')}",
        f"Product: {lot.get('product_name', '-')}",
        f"SKU: {lot.get('sku', '-')}",
    ]
    if lot.get("barcode"):
        lines.append(f"Barcode: {lot['barcode']}")
    if lot.get("batch_no"):
        lines.append(f"Batch: {lot['batch_no']}")
    lines.append(f"Expiry date: {lot.get('expiry_date', '-')}")
    remaining = lot.get("remaining_qty")
    lines.append(f"Remaining qty: {remaining if remaining is not None else '-'}")
    if days_until_expiry < 0:
        lines.append(f"Status: EXPIRED {-days_until_expiry} day(s) ago")
    elif days_until_expiry == 0:
        lines.append("Status: expires TODAY")
    else:
        lines.append(f"Days remaining: {days_until_expiry}")
    return "\n".join(lines)


class ExpiryAlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ExpiryAlertRepository(session)

    async def _alert_windows(self) -> dict[int, int]:
        alert_1 = await get_setting_value(
            self.session, "stock", "expiry_alert_1_days", DEFAULT_ALERT_1_DAYS
        )
        alert_2 = await get_setting_value(
            self.session, "stock", "expiry_alert_2_days", DEFAULT_ALERT_2_DAYS
        )
        try:
            windows = {ALERT_LEVEL_1: int(alert_1), ALERT_LEVEL_2: int(alert_2)}
        except (TypeError, ValueError):
            logger.warning("Invalid expiry alert windows configured; falling back to defaults")
            windows = {ALERT_LEVEL_1: DEFAULT_ALERT_1_DAYS, ALERT_LEVEL_2: DEFAULT_ALERT_2_DAYS}
        return {level: max(0, days) for level, days in windows.items()}

    async def _enabled(self) -> bool:
        return bool(
            await get_setting_value(self.session, "telegram", "expiry_alerts_enabled", True)
        )

    async def _recipients(self) -> list[str]:
        result = await self.session.execute(
            select(User.telegram_chat_id).where(
                User.status == "ACTIVE",
                User.telegram_verified.is_(True),
                User.telegram_chat_id.is_not(None),
                User.telegram_chat_id != "",
            )
        )
        return [str(chat_id) for chat_id in result.scalars().all()]

    async def scan_and_send(
        self,
        *,
        sender: Sender | None = None,
        today: date | None = None,
    ) -> dict:
        """Run one alert sweep. Returns a summary for the calling task.

        ``sender`` is injectable for tests; production uses the shared
        Telegram client. Never raises on delivery problems — delivery
        failures simply leave the state row unwritten so the next scan
        retries. Commits its own transaction.
        """
        sender = sender or _default_sender
        today = today or date.today()

        if not await self._enabled():
            return {"enabled": False, "lots": 0, "sent": 0, "levels": {}}

        windows = await self._alert_windows()
        lots = await self.repo.expiring_lots()
        already_sent = await self.repo.sent_levels()

        levels_sent = {ALERT_LEVEL_1: 0, ALERT_LEVEL_2: 0}
        for lot in lots:
            days_until = (lot["expiry_date"] - today).days
            batch_key = lot["batch_no"] or ""
            for level, window_days in windows.items():
                if days_until > window_days:
                    continue  # outside this alert window
                key = (lot["product_id"], batch_key, lot["expiry_date"], level)
                if key in already_sent:
                    continue  # at most once per lot/level
                text = format_expiry_alert_text(
                    lot, alert_level=level, days_until_expiry=days_until
                )
                delivered = 0
                for chat_id in await self._recipients():
                    try:
                        if await sender(chat_id, text):
                            delivered += 1
                    except Exception:  # noqa: BLE001 — one bad recipient must not stop the sweep
                        logger.exception("Expiry alert send failed for chat %s", chat_id)
                if delivered == 0:
                    # Nothing delivered (no recipients or Telegram down):
                    # leave state unwritten so the next scan retries.
                    continue
                self.repo.record_state(
                    product_id=lot["product_id"],
                    batch_no=lot["batch_no"],
                    expiry_date=lot["expiry_date"],
                    alert_level=level,
                )
                already_sent.add(key)
                levels_sent[level] += 1

        await self.session.commit()
        return {
            "enabled": True,
            "lots": len(lots),
            "sent": sum(levels_sent.values()),
            "levels": levels_sent,
        }


async def _default_sender(chat_id: str, text: str) -> bool:
    from app.shared.telegram.client import send_message

    return await send_message(chat_id, text)
