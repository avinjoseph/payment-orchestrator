import time
from typing import Literal
from redis.asyncio import Redis

BreakerState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class CircuitBreaker:
    def __init__(self, 
                 gateway: str,
                 redis: Redis,
                 fail_threshold: int = 3,
                 window_seconds: int = 10,
                 cooldown_seconds: int = 15,
                 trail_timeout_ms: int = 3000,):
        
        self.gateway = gateway
        self.redis = redis
        self.fail_threshold = fail_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.trial_timeout_ms = trail_timeout_ms
        
        self._state_key = f"breaker:{gateway}:state"
        self._failures_key = f"breaker:{gateway}:failures"
        self._opened_at_key = f"breaker:{gateway}:opened_at"
        self._trial_lock_key = f"breaker:{gateway}:trial_lock"
        
    async def get_state(self) -> BreakerState:
        raw_state = await self.redis.get(self._state_key)
        if raw_state == "OPEN":
            opened_at_str = await self.redis.get(self._opened_at_key)
            if opened_at_str:
                elapsed = time.time() - float(opened_at_str)
                if elapsed >= self.cooldown_seconds:
                    return "HALF_OPEN"
            return "OPEN"
        return "CLOSED"
    
    async def is_call_allowed(self) -> bool:
        state = await self.get_state()
        if state == "CLOSED":
            return True
        if state == "OPEN":
            return False
        if state == "HALF_OPEN":
            # Atomic check-and-set so only one concurrent request runs the trial
            acquired = await self.redis.set(
                self._trial_lock_key,
                "1",
                nx=True,
                px=self.trial_timeout_ms
            )
            return bool(acquired)
        return False
        
    async def record_success(self) -> None:
        state = await self.get_state()
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(self._failures_key)
            pipe.delete(self._trial_lock_key)
            if state in ["OPEN", "HALF_OPEN"]:
                pipe.set(self._state_key, "CLOSED")
                pipe.delete(self._opened_at_key)
            await pipe.execute()

    async def record_failure(self) -> None:
        state = await self.get_state()
        if state == "HALF_OPEN":
            # Failed trial -> immediately push back to OPEN
            await self.redis.set(self._state_key, "OPEN")
            await self.redis.set(self._opened_at_key, str(time.time()))
            await self.redis.delete(self._trial_lock_key)
            return
        
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(self._failures_key)
            pipe.expire(self._failures_key, self.window_seconds)
            results = await pipe.execute()
            
        failure_count = results[0]
        if failure_count >= self.fail_threshold:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.set(self._state_key, "OPEN")
                pipe.set(self._opened_at_key, str(time.time()))
                await pipe.execute()