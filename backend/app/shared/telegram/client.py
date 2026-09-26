"""Telegram Bot API client.

The bot token lives only in Administration > Settings
(`system_settings.telegram.bot_token`); there is no environment fallback so the
SPA is the single source of truth. A pooled ``httpx.AsyncClient`` is cached per
running event loop so back-to-back sends reuse the TLS connection instead of
paying a new handshake per recipient.
"""

import asyncio
import logging
import threading
import weakref

import httpx

logger = logging.getLogger("stock_pos.telegram")

API_BASE = "https://api.telegram.org"

# One AsyncClient per event loop: the API process, the bot process and each
# test loop get their own pooled client (httpx clients are loop-bound).
_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
    weakref.WeakKeyDictionary()
)
_clients_lock = threading.Lock()


def _get_http_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    with _clients_lock:
        client = _clients.get(loop)
        if client is None or getattr(client, "is_closed", False):
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
            _clients[loop] = client
        return client


async def aclose_telegram_clients() -> None:
    """Close every pooled client (call on API/bot shutdown)."""
    with _clients_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            logger.debug("Failed to close a Telegram HTTP client", exc_info=True)


async def resolve_bot_token(session=None) -> str:
    """Return the bot token saved in Administration > Settings.

    The value is intentionally kept inside the backend and must never be
    included in API output or logs. Returns an empty string when no token has
    been saved yet.
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
        return str(saved or "").strip()
    except Exception:  # noqa: BLE001 - delivery stays best-effort
        logger.warning("Could not load the saved Telegram bot token")
        return ""


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
    delivery errors to end users. Uses the per-loop pooled client.
    """
    token = str(bot_token or "").strip() or await resolve_bot_token(session)
    if not token:
        logger.warning("Telegram delivery skipped: no bot token saved in Settings")
        return False
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        response = await _get_http_client().post(url, json=payload)
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
