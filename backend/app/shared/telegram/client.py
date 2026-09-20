"""Telegram Bot API client with database secret and environment fallback."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("stock_pos.telegram")

API_BASE = "https://api.telegram.org"


async def resolve_bot_token(session=None) -> str:
    """Return the saved bot token, falling back to TELEGRAM_BOT_TOKEN.

    The value is intentionally kept inside the backend and must never be
    included in API output or logs.
    """
    try:
        from app.modules.administration.service import get_setting_value

        if session is not None:
            saved = await get_setting_value(session, "telegram", "bot_token", "")
        else:
            from app.core.database import SessionFactory

            async with SessionFactory() as lookup_session:
                saved = await get_setting_value(
                    lookup_session, "telegram", "bot_token", ""
                )
        token = str(saved or "").strip()
        if token:
            return token
    except Exception:  # noqa: BLE001 - environment fallback keeps delivery best-effort
        logger.warning("Could not load the saved Telegram bot token; using environment fallback")
    return str(settings.telegram_bot_token or "").strip()


async def send_message(
    chat_id: str,
    text: str,
    *,
    bot_token: str | None = None,
    session=None,
    parse_mode: str | None = None,
) -> bool:
    """Send a message via the Telegram Bot API. Returns True on success.

    `parse_mode` enables Telegram formatting (the notification cards send
    "HTML" for bold titles and monospace codes). Fails soft (returns False)
    when Telegram is not configured or unreachable; callers must not leak
    delivery errors to end users.
    """
    token = str(bot_token or "").strip() or await resolve_bot_token(session)
    if not settings.telegram_enabled or not token:
        logger.warning("Telegram delivery skipped: bot token not configured")
        return False
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            # Log Telegram's own description so an operator can tell an invalid
            # token (401) from "chat not found" (400) or a blocked bot (403).
            logger.error(
                "Telegram sendMessage failed: HTTP %s %s",
                response.status_code,
                response.text[:500],
            )
            return False
    except httpx.HTTPError as exc:
        logger.error("Telegram sendMessage error: %s", exc)
        return False
