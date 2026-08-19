from typing import AsyncGenerator
from redis.asyncio import Redis, from_url
from app.config import settings

redis_pool: Redis | None = None

async def init_redis() -> Redis:
    global redis_pool
    if redis_pool is None:
        redis_pool = from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        
    return redis_pool

async def get_redis_client() -> Redis:
    if redis_pool is None:
        return await init_redis()
    return redis_pool

async def close_redis():
    global redis_pool
    if redis_pool is not None:
        await redis_pool.close()
        redis_pool = None