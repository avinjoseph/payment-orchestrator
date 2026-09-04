# app/core/redis_client.py
from redis.asyncio import Redis

from app.config import settings


def get_redis_client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )


async def close_redis() -> None:
    pass