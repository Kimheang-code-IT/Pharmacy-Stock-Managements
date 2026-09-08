"""In-process Telegram delivery. The API sends HTTP to Telegram — no Celery worker."""

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger("stock_pos.telegram")

RESET_CODE_TEXT = "Your Stock & POS password reset code is {code}. It expires in {minutes} minutes."
RESET_LINK_TEXT = "Or reset directly: {link}"


def queue_reset_code_delivery(chat_id: str, code: str, *, handoff_token: str | None = None) -> bool:
    """Send a password-reset code from this API process (best effort).

    Returns True when a send task was scheduled. Delivery errors must never
    leak to the HTTP caller beyond a logged failure.
    """
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        logger.warning("Telegram reset-code delivery skipped: bot token not configured")
        return False
    text = RESET_CODE_TEXT.format(
        code=code,
        minutes=settings.telegram_reset_code_expire_minutes,
    )
    if handoff_token and settings.frontend_base_url:
        base = settings.frontend_base_url.rstrip("/")
        text += "\n" + RESET_LINK_TEXT.format(link=f"{base}/auth/reset-password?handoff={handoff_token}")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("Telegram reset-code send skipped: no running event loop")
        return False

    async def _send() -> None:
        from app.shared.telegram.client import send_message

        ok = await send_message(str(chat_id), text)
        if not ok:
            logger.error("Telegram reset-code send failed for chat %s", chat_id)

    loop.create_task(_send())
    return True
