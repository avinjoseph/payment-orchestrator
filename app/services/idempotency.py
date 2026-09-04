import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis

from app.services.exceptions import IdempotencyConflictError


class IdempotencyManager:
    def __init__(self, redis: Redis, lock_ttl_ms: int = 5000, cache_ttl_sec: int = 86400):
        self.redis = redis
        self.lock_ttl_ms = lock_ttl_ms
        self.cache_ttl_sec = cache_ttl_sec
        
    def _lock_key(self, key: str) -> str:
        return f"idem:lock:{key}"
    
    def _data_key(self, key: str) -> str:
        return f"idem:data:{key}"
    
    async def get_cached_response(self, idempotency_key:str) -> dict[str, Any] | None:
        cached_response = await self.redis.get(self._data_key(idempotency_key))
        if cached_response:
            return json.loads(cached_response)
        return None
    
    async def cache_response(self, idempotency_key:str, response: dict[str, Any]) -> None:
        await self.redis.set(
            self._data_key(idempotency_key),
            json.dumps(response),
            ex=self.cache_ttl_sec,
        )

    async def acquire(self, idempotency_key: str) -> bool:
        return bool(
            await self.redis.set(
                self._lock_key(idempotency_key),
                "1",
                nx=True,
                px=self.lock_ttl_ms,
            )
        )

    async def release(self, idempotency_key: str) -> None:
        await self.redis.delete(self._lock_key(idempotency_key))
        
    @asynccontextmanager
    async def acquire_lock(self, idempotency_key:str) -> AsyncGenerator[None, None]:
        # lock_key = self._lock_key(idempotency_key)
        lock_acquired = await self.acquire(idempotency_key)
        
        if not lock_acquired:
            deadline = time.monotonic() + (self.lock_ttl_ms / 1000)
            while time.monotonic() < deadline:
                cached_response = await self.get_cached_response(idempotency_key)
                if cached_response:
                    yield
                    return
                await asyncio.sleep(0.01)
            raise IdempotencyConflictError(idempotency_key)
        
        try:
            yield
        finally:
            await self.release(idempotency_key)
    