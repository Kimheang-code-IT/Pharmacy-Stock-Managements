"""In-process Telegram delivery. The API sends HTTP to Telegram — no Celery worker."""

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger("stock_pos.telegram")

_RESET_TITLES = {
    "en": "Password Reset Code",
    "km": "លេខកូដកំណត់ពាក្យសម្ងាត់ឡើងវិញ",
}
_RESET_BODIES = {
    "en": "Your password reset code is:\n\n{code}\n\nIt expires in {minutes} minutes.",
    "km": "លេខកូដកំណត់ពាក្យសម្ងាត់របស់អ្នកគឺ:\n\n{code}\n\nផុតកំណត់ក្នុងរយៈពេល {minutes} នាទី។",
}
_RESET_LINKS = {
    "en": "Or reset directly:",
    "km": "ឬកំណត់ឡើងវិញដោយផ្ទាល់:",
}


def normalize_language(value) -> str:
    return "km" if str(value or "").strip().lower() == "km" else "en"


def format_reset_code_text(
    code: str, minutes: int, *, handoff_url: str | None = None, lang: str = "en"
) -> str:
    """Card-style (Telegram HTML) password-reset message with the code in a
    monospace block. `lang` follows the Settings notification language."""
    language = normalize_language(lang)
    lines = [
        f"🔐 <b>{_RESET_TITLES[language]}</b>",
        "",
        _RESET_BODIES[language].format(code=f"<code>{code}</code>", minutes=minutes),
    ]
    if handoff_url:
        lines += ["", f"{_RESET_LINKS[language]} {handoff_url}"]
    return "\n".join(lines)


async def _notification_language(session) -> str:
    from app.modules.administration.service import get_setting_value

    return normalize_language(
        await get_setting_value(session, "telegram", "notification_language", "en")
    )


def queue_reset_code_delivery(
    chat_id: str, code: str, *, handoff_token: str | None = None, minutes: int | None = None
) -> bool:
    """Send a password-reset code from this API process (best effort).

    Returns True when a send task was scheduled. Delivery errors must never
    leak to the HTTP caller beyond a logged failure.
    """
    ttl = minutes if minutes and minutes > 0 else settings.telegram_reset_code_expire_minutes
    base = settings.frontend_base_url.rstrip("/") if settings.frontend_base_url else ""
    handoff_url = (
        f"{base}/auth/reset-password?handoff={handoff_token}"
        if handoff_token and base
        else None
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("Telegram reset-code send skipped: no running event loop")
        return False

    async def _send() -> None:
        from app.core.database import SessionFactory
        from app.shared.telegram.client import send_message

        language = "en"
        try:
            async with SessionFactory() as session:
                language = await _notification_language(session)
        except Exception:  # noqa: BLE001 - fall back to English, never fail the send
            logger.warning("Could not read the notification language; using English")
        text = format_reset_code_text(code, ttl, handoff_url=handoff_url, lang=language)
        ok = await send_message(str(chat_id), text, parse_mode="HTML")
        if not ok:
            logger.error("Telegram reset-code send failed for chat %s", chat_id)

    loop.create_task(_send())
    return True
