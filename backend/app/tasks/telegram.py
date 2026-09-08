"""Queued Telegram delivery tasks for the worker-telegram Celery worker."""

import asyncio

from app.tasks.celery_app import celery


@celery.task(name="app.tasks.telegram.send_reset_code", bind=True, max_retries=3, default_retry_delay=5)
def send_reset_code(self, chat_id: str, code: str) -> bool:
    from app.core.config import settings
    from app.shared.telegram.client import send_message

    text = f"Your Stock & POS password reset code is {code}. It expires in {settings.telegram_reset_code_expire_minutes} minutes."
    success = asyncio.run(send_message(chat_id, text))
    if not success:
        raise self.retry(exc=RuntimeError("Telegram sendMessage failed"))
    return True


@celery.task(name="app.tasks.telegram.scan_expiry_alerts", bind=True, max_retries=3, default_retry_delay=30)
def scan_expiry_alerts(self) -> dict:
    """Daily expiry alert sweep (spec section 3.6, use case 2).

    Triggered by the in-process API scheduler; never invoked from the
    HTTP path. Sends once per product/batch/expiry lot per alert level and
    persists `telegram_expiry_alert_state`. Read-only with respect to stock:
    this job never mutates balances or movements.
    """
    from app.core.database import SessionFactory
    from app.modules.telegram.service import ExpiryAlertService

    async def _run() -> dict:
        async with SessionFactory() as session:
            return await ExpiryAlertService(session).scan_and_send()

    try:
        summary = asyncio.run(_run())
    except Exception as exc:  # transient DB/config issues — retry via celery
        raise self.retry(exc=exc) from exc
    if summary.get("enabled"):
        import logging

        logging.getLogger("stock_pos.telegram").info(
            "Expiry alert sweep: %s", summary
        )
    return summary


@celery.task(name="app.tasks.telegram.send_payment_invoice", bind=True, max_retries=3, default_retry_delay=5)
def send_payment_invoice(self, payload: dict) -> int:
    """Deliver the payment/invoice text summary to verified staff (spec 3.6.2).

    Recipients, shop name and app timezone are resolved from the database here
    so the API hook stays a single fire-and-forget enqueue. Read-only: this
    task never mutates business data.
    """
    from sqlalchemy import select

    from app.core.config import settings

    if not settings.telegram_enabled or not settings.telegram_bot_token:
        return 0

    async def _deliver() -> tuple[int, int]:
        from app.core.database import SessionFactory
        from app.modules.administration.service import get_setting_value
        from app.modules.auth.models import User
        from app.shared.telegram.client import send_message
        from app.shared.telegram.notify import format_payment_invoice_text

        async with SessionFactory() as session:
            result = await session.execute(
                select(User.telegram_chat_id).where(
                    User.status == "ACTIVE",
                    User.telegram_verified.is_(True),
                    User.telegram_chat_id.is_not(None),
                    User.telegram_chat_id != "",
                )
            )
            recipients = [str(chat_id) for chat_id in result.scalars().all()]
            shop_name = await get_setting_value(session, "shop", "shop_name", "Yoeun Sokhon Pharmacy")
            timezone_name = await get_setting_value(session, "system", "timezone", "UTC")

        text = format_payment_invoice_text(
            payload,
            shop_name=str(shop_name or "Yoeun Sokhon Pharmacy"),
            timezone_name=str(timezone_name or "UTC"),
        )
        sent = 0
        for chat_id in recipients:
            if await send_message(chat_id, text):
                sent += 1
        return sent, len(recipients)

    sent, total = asyncio.run(_deliver())
    if total and sent == 0:
        raise self.retry(exc=RuntimeError("Telegram payment notify delivery failed"))
    return sent
