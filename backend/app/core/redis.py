import json
import logging
from typing import Any

from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("stock_pos.redis")

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


class CacheClient:
    """Redis-backed cache that degrades gracefully when Redis is unavailable."""

    def __init__(self, client: aioredis.Redis | None = None) -> None:
        self._client = client

    def _get_client(self) -> aioredis.Redis | None:
        if self._client is not None:
            return self._client
        try:
            return get_redis()
        except Exception:
            return None

    async def get_json(self, key: str) -> Any | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            raw = await client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("redis get failed for %s: %s", key, exc)
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            await client.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:
            logger.warning("redis set failed for %s: %s", key, exc)

    async def delete_prefix(self, prefix: str) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=f"{prefix}*", count=200)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("redis delete_prefix failed for %s: %s", prefix, exc)

    async def delete_keys(self, *keys: str) -> None:
        client = self._get_client()
        if client is None or not keys:
            return
        try:
            await client.delete(*keys)
        except Exception as exc:
            logger.warning("redis delete failed: %s", exc)

    async def ping(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            return bool(await client.ping())
        except Exception:
            return False


cache = CacheClient()
