# app/core/rate_limiter.py
import time

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.core.redis_client import get_redis_client


class SlidingWindowRateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        now = time.time()
        clear_before = now - window_seconds
        key = f"ratelimit:{identifier}"

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, clear_before)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()

        request_count = results[2]

        if request_count > limit:
            retry_after = int(window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds}s.",
                headers={"Retry-After": str(retry_after)},
            )


async def enforce_rate_limit(
    identifier: str,
    limit: int = 120,
    window_seconds: int = 60,
) -> None:
    redis = get_redis_client()
    try:
        limiter = SlidingWindowRateLimiter(redis=redis)
        await limiter.check_rate_limit(identifier, limit, window_seconds)
    finally:
        await redis.aclose()