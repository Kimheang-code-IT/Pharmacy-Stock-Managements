"""Telegram Bot API client. Secrets come from environment only (backend-side)."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("stock_pos.telegram")

API_BASE = "https://api.telegram.org"


async def send_message(chat_id: str, text: str) -> bool:
    """Send a message via the Telegram Bot API. Returns True on success.

    Fails soft (returns False) when Telegram is not configured or unreachable;
    callers must not leak delivery errors to end users.
    """
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        logger.warning("Telegram delivery skipped: bot token not configured")
        return False
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            logger.error("Telegram sendMessage failed: HTTP %s", response.status_code)
            return False
    except httpx.HTTPError as exc:
        logger.error("Telegram sendMessage error: %s", exc)
        return False
