import json 
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any
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
        
    @asynccontextmanager
    async def acquire_lock(self, idempotency_key:str) -> AsyncGenerator[None, None]:
        lock_key = self._lock_key(idempotency_key)
        lock_acquired = await self.redis.set(lock_key, "1", nx=True, px=self.lock_ttl_ms)
        
        if not lock_acquired:
            raise IdempotencyConflictError(idempotency_key)
        
        try:
            yield
        finally:
            await self.redis.delete(lock_key)
    