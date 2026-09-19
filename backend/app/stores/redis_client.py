import asyncio

import redis.asyncio as redis_async

from app.config import get_settings

_redis: redis_async.Redis | None = None


def get_redis() -> redis_async.Redis:
    global _redis
    if _redis is None:
        _redis = redis_async.from_url(get_settings().redis_url)
    return _redis


async def check() -> bool:
    try:
        async with asyncio.timeout(3):
            return bool(await get_redis().ping())
    except Exception:
        return False
