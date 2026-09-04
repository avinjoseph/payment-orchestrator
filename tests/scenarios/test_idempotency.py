# tests/scenarios/test_idempotency.py
import asyncio

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.redis_client import get_redis_client
from app.db.models import Transactions
from app.db.session import AsyncSessionLocal
from app.services.health_monitor import GatewayHealthMonitor


@pytest.mark.scenario
@respx.mock
async def test_concurrent_duplicate_requests_only_charge_once(client: AsyncClient):
    redis = get_redis_client()
    try:
        monitor = GatewayHealthMonitor(redis=redis)
        # Seed Stripe as the highest scoring gateway
        await monitor.record_outcome("stripe", success=True, latency_ms=10)
        await monitor.refresh_scores(["stripe", "razorpay"])
    finally:
        await redis.aclose()

    stripe_route = respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=httpx.Response(200, json={
            "id": "pi_stripe_idem_single",
            "status": "succeeded"
        })
    )

    idem_key = "scenario-idempotent-race-key"
    payload = {
        "amount": 10000,
        "currency": "USD",
        "method": "card",
        "customer_ref": "cust_concurrent_race"
    }

    responses = await asyncio.gather(
        client.post("/payments", json=payload, headers={"Idempotency-Key": idem_key}),
        client.post("/payments", json=payload, headers={"Idempotency-Key": idem_key}),
        return_exceptions=True
    )

    valid_responses = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 201]
    assert len(valid_responses) >= 1

    async with AsyncSessionLocal() as db:
        stmt = select(func.count(Transactions.id)).where(Transactions.idempotency_key == idem_key)
        count = (await db.execute(stmt)).scalar()
        assert count == 1

    assert stripe_route.call_count == 1