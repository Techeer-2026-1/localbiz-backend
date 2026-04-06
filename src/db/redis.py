"""Redis 클라이언트 — 외부 API 응답 캐싱 전용"""

import json
from typing import Any

import aioredis

from backend.src.config import get_settings

settings = get_settings()

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.close()
        _redis = None


import logging

logger = logging.getLogger(__name__)


async def cache_get(key: str) -> Any | None:
    try:
        r = await get_redis()
        value = await r.get(key)
        if value is None:
            return None
        return json.loads(value)
    except (aioredis.exceptions.ConnectionError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"Redis cache_get failed: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except (aioredis.exceptions.ConnectionError, Exception) as e:
        logger.warning(f"Redis cache_set failed: {e}")


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except (aioredis.exceptions.ConnectionError, Exception) as e:
        logger.warning(f"Redis cache_delete failed: {e}")
