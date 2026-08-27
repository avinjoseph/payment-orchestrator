# tests/test_phase4.py
import asyncio
import time

import pytest

from app.core.redis_client import get_redis_client
from app.db.models import Transactions
from app.db.session import AsyncSessionLocal
from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError
from app.gateways.registry import GatewayRegistry
from app.services.circuit_breaker import CircuitBreaker
from app.services.exceptions import AllGatewaysExhaustedError
from app.services.failover import FailoverEngine
from app.services.state_machine import TransactionStateMachine


class SlowGatewayMock(GatewayAdapter):
    def __init__(self, name: str, delay_sec: float):
        self.name = name
        self.delay_sec = delay_sec

    async def charge(self, amount: int, currency: str, method: str, idempotency_key: str) -> GatewayResponse:
        await asyncio.sleep(self.delay_sec)
        return GatewayResponse(status="success", gateway_txn_id=f"{self.name}_123")

    async def get_status(self, gateway_txn_id: str) -> GatewayResponse:
        return GatewayResponse(status="success")

    async def refund(self, gateway_txn_id: str, amount: int) -> GatewayResponse:
        return GatewayResponse(status="success")

    def verify_webhook(self, payload: bytes, headers: dict) -> bool:
        return True


@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    redis = await get_redis_client()
    cb = CircuitBreaker(
        gateway="cb_test_gw",
        redis=redis,
        fail_threshold=2,
        window_seconds=5,
        cooldown_seconds=1
    )

    assert await cb.get_state() == "CLOSED"
    assert await cb.is_call_allowed() is True

    # Record 2 failures -> Breaker opens
    await cb.record_failure()
    await cb.record_failure()

    assert await cb.get_state() == "OPEN"
    assert await cb.is_call_allowed() is False

    # Wait for cooldown -> transitions to HALF_OPEN
    await asyncio.sleep(1.1)
    assert await cb.get_state() == "HALF_OPEN"
    assert await cb.is_call_allowed() is True

    # Successful trial closes breaker
    await cb.record_success()
    assert await cb.get_state() == "CLOSED"


@pytest.mark.asyncio
async def test_failover_recovers_within_2s_budget():
    redis = await get_redis_client()
    registry = GatewayRegistry()

    # Primary gateway times out (> 800ms)
    registry.register("gw_slow", SlowGatewayMock("gw_slow", delay_sec=1.5), {"USD"}, {"card"})
    # Secondary gateway succeeds quickly (100ms)
    registry.register("gw_fast", SlowGatewayMock("gw_fast", delay_sec=0.1), {"USD"}, {"card"})

    async with AsyncSessionLocal() as db:
        txn = Transactions(
            idempotency_key="failover-test-01",
            amount=5000,
            currency="USD",
            status="created"
        )
        db.add(txn)
        await db.commit()

        state_machine = TransactionStateMachine(db=db)
        engine = FailoverEngine(redis=redis, state_machine=state_machine, registry=registry)

        start_time = time.perf_counter()
        result = await engine.charge_with_failover(
            transaction_id=txn.id,
            amount=5000,
            currency="USD",
            method="card",
            idempotency_key="failover-test-01"
        )
        elapsed = time.perf_counter() - start_time

        assert result.gateway_name == "gw_fast"
        assert result.attempted_gateways == ["gw_slow", "gw_fast"]
        assert elapsed < 2.0  # Proven sub-2s recovery