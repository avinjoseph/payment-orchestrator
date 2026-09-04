# tests/scenarios/test_failover.py
import time

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.redis_client import get_redis_client
from app.db.models import Transactions
from app.db.session import AsyncSessionLocal
from app.services.health_monitor import GatewayHealthMonitor


@pytest.mark.scenario
@respx.mock
async def test_failover_completes_within_budget(client: AsyncClient):
    # Ensure Razorpay is picked first (health score 1.0 vs 0.9 for stripe)
    redis = get_redis_client()
    try:
        monitor = GatewayHealthMonitor(redis=redis)
        await monitor.record_outcome("razorpay", success=True, latency_ms=50)
        await monitor.record_outcome("stripe", success=True, latency_ms=150)
        await monitor.refresh_scores(["razorpay", "stripe"])
    finally:
        await redis.aclose()

    # Razorpay times out
    respx.post("https://api.razorpay.com/v1/payments").mock(
        side_effect=httpx.TimeoutException("Simulated connection timeout on Razorpay")
    )
    # Stripe succeeds immediately
    respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=httpx.Response(200, json={
            "id": "pi_stripe_recovered_1",
            "status": "succeeded"
        })
    )

    idem_key = "scenario-failover-test-01"
    start_time = time.perf_counter()

    res = await client.post(
        "/payments",
        json={
            "amount": 2500,
            "currency": "USD",
            "method": "card",
            "customer_ref": "cust_failover_user"
        },
        headers={"Idempotency-Key": idem_key}
    )

    elapsed_time = time.perf_counter() - start_time

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "captured"
    assert data["gateway"] == "stripe"
    assert elapsed_time < 2.0

    async with AsyncSessionLocal() as db:
        txn = await db.get(Transactions, data["id"])
        assert txn is not None
        assert len(txn.events) >= 3