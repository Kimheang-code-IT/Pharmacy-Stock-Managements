"""Telegram account linking (`/link CODE`).

The user generates a one-time code in the app (POST /auth/telegram/link-code,
stored in Redis by the API) and sends it to the bot. The bot consumes the
code and binds its chat to the user account. This is the only write the bot
process performs, and it only ever sets `telegram_chat_id` /
`telegram_verified` on the user named by the code.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.modules.auth.models import User

logger = logging.getLogger("stock_pos.telegram")

TELEGRAM_LINK_PREFIX = "tglink"  # must match app.modules.auth.service


async def consume_link_code(session: AsyncSession, code: str, chat_id: str) -> User | None:
    """Bind `chat_id` to the user identified by a valid, unexpired code.

    Returns the linked user, or None when the code is unknown/expired.
    The code is single use — it is deleted before the DB write.
    """
    normalized = (code or "").strip().upper()
    if not normalized or not chat_id:
        return None
    client = get_redis()
    try:
        raw = await client.get(f"{TELEGRAM_LINK_PREFIX}:{normalized}")
    except Exception as exc:
        logger.error("Failed to read telegram link code: %s", exc)
        return None
    if not raw:
        return None
    try:
        await client.delete(f"{TELEGRAM_LINK_PREFIX}:{normalized}")
        user_id = json.loads(raw)["user_id"]
    except Exception as exc:
        logger.error("Failed to consume telegram link code: %s", exc)
        return None

    user = await session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        return None
    user.telegram_chat_id = str(chat_id)
    user.telegram_verified = True
    await session.commit()
    return user
