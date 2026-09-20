"""Diagnose Telegram bot connectivity (why "Test connection" fails).

Usage (inside the api container, from the infrastructure folder):

    docker compose exec api python scripts/telegram_check.py

It resolves the saved bot token, calls Telegram `getMe`, then sends one test
message to the configured Chat/Group ID and prints Telegram's raw response. The
HTTP status + description tell you exactly what is wrong:

- 401 Unauthorized        → the token is wrong/revoked; re-copy it from @BotFather.
- 400 chat not found      → nobody started this bot from that chat; open
                            https://t.me/<bot_username>, press Start, then use the
                            ID the bot replies with (or link the user, see below).
- 403 Forbidden           → the user blocked the bot.
- Network/DNS error       → the API container cannot reach api.telegram.org.

Nothing is written to the database.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

# Make `app` importable when run as `python scripts/telegram_check.py` from the
# backend folder (Python puts the script's folder, not the CWD, on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API_BASE = "https://api.telegram.org"


async def main() -> int:
    # Import the models that SystemSetting's foreign keys reference so the first
    # query does not fail on an unresolved mapper in this standalone process.
    import app.modules.administration.models  # noqa: F401
    import app.modules.auth.models  # noqa: F401

    from app.core.database import SessionFactory
    from app.modules.administration.service import get_setting_value
    from app.shared.telegram.client import resolve_bot_token

    async with SessionFactory() as session:
        token = await resolve_bot_token(session)
        enabled = await get_setting_value(session, "telegram", "enabled", True)
        chat_id = str(await get_setting_value(session, "telegram", "chat_id", "") or "").strip()

    if not token:
        print("No bot token configured.")
        print("Open Settings > Telegram, paste the token from @BotFather, and Save changes.")
        return 1

    print(f"Bot token: {token[:8]}...{token[-4:]} (length {len(token)})")
    print(f"Telegram enabled: {enabled}")
    print(f"Configured Chat/Group ID: {chat_id or '(none)'}")

    async with httpx.AsyncClient(timeout=15) as client:
        me = await client.get(f"{API_BASE}/bot{token}/getMe")
        print(f"\ngetMe -> HTTP {me.status_code}: {me.text[:400]}")
        if me.status_code != 200:
            print("\nThe token itself is rejected. Re-copy it from @BotFather.")
            return 1

        result = me.json().get("result", {})
        username = result.get("username")
        if username:
            print(f"Bot username: @{username}")

        if not chat_id:
            print("\nNo Chat/Group ID set. Either set one in Settings > Telegram,")
            print("or link a user under Administration > Users (Telegram Chat ID).")
            return 1

        sent = await client.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "Stock & POS - Telegram test message"},
        )
        print(f"\nsendMessage({chat_id}) -> HTTP {sent.status_code}: {sent.text[:400]}")

    if sent.status_code == 200:
        print("\nOK: Telegram accepted the message. Notifications will be delivered.")
        return 0

    print("\nTelegram rejected the message. Common causes:")
    print("  401 → invalid/revoked token.")
    print("  400 chat not found → open https://t.me/%s and press Start," % (username or "<bot_username>"))
    print("        then use the Chat ID the bot replies with on /start.")
    print("  403 → the user blocked the bot.")
    print("  DNS/network → the API container cannot reach api.telegram.org.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except httpx.HTTPError as exc:
        print(f"Network error reaching Telegram: {exc}")
        sys.exit(2)
