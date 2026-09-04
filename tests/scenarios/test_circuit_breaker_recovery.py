# tests/scenarios/test_circuit_breaker_recovery.py
import asyncio

import pytest

from app.core.redis_client import get_redis_client
from app.services.circuit_breaker import CircuitBreaker


@pytest.mark.scenario
async def test_circuit_breaker_full_lifecycle():
    redis = await get_redis_client()
    breaker = CircuitBreaker(
        gateway="rzp_lifecycle",
        redis=redis,
        fail_threshold=3,
        window_seconds=5,
        cooldown_seconds=1,
        trial_timeout_ms=500
    )

    # 1. Closed state initially
    assert await breaker.get_state() == "CLOSED"
    assert await breaker.is_call_allowed() is True

    # 2. Accumulate failures -> Transition to OPEN
    for _ in range(3):
        await breaker.record_failure()

    assert await breaker.get_state() == "OPEN"
    assert await breaker.is_call_allowed() is False

    # 3. Wait for cooldown expiration -> Transition to HALF_OPEN
    await asyncio.sleep(1.1)
    assert await breaker.get_state() == "HALF_OPEN"

    # Only single trial allowed concurrently
    assert await breaker.is_call_allowed() is True
    assert await breaker.is_call_allowed() is False

    # 4. Successful trial recovers to CLOSED
    await breaker.record_success()
    assert await breaker.get_state() == "CLOSED"
    assert await breaker.is_call_allowed() is True