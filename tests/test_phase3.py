# tests/test_phase3.py

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.redis_client import get_redis_client
from app.gateways.mock import MockGatewayAdapter
from app.gateways.registry import GatewayRegistry
from app.services.health_monitor import GatewayHealthMonitor
from app.services.router import SmartRouter


@pytest.mark.asyncio
async def test_health_monitor_and_routing():
    redis = await get_redis_client()
    monitor = GatewayHealthMonitor(redis=redis, window_minutes=2)

    # Simulate Gateway A degrading
    for _ in range(5):
        await monitor.record_outcome(gateway="gw_a", success=False, latency_ms=1800)
    
    # Simulate Gateway B healthy
    for _ in range(5):
        await monitor.record_outcome(gateway="gw_b", success=True, latency_ms=120)

    score_a = await monitor.compute_health_score("gw_a")
    score_b = await monitor.compute_health_score("gw_b")
    
    assert score_b > score_a

    await monitor.refresh_scores(["gw_a", "gw_b"])

    custom_registry = GatewayRegistry()
    custom_registry.register("gw_a", MockGatewayAdapter(name="gw_a"), {"USD"}, {"card"})
    custom_registry.register("gw_b", MockGatewayAdapter(name="gw_b"), {"USD"}, {"card"})

    router = SmartRouter(health_monitor=monitor, registry=custom_registry)
    selected = await router.select_gateway(method="card", currency="USD")
    assert selected == "gw_b"


# In tests/test_phase3.py
@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_multi_gateway_flow(async_client: AsyncClient):
    respx.post("https://api.razorpay.com/v1/payments").mock(
        return_value=httpx.Response(200, json={
            "id": "pay_upi_phase3_1",
            "status": "captured"
        })
    )

    idempotency_key = "test-phase3-upi-flow"
    res = await async_client.post(
        "/payments",
        json={
            "amount": 50000,
            "currency": "INR",
            "method": "upi",
            "customer_ref": "cust_upi_1"
        },
        headers={"Idempotency-Key": idempotency_key}
    )

    assert res.status_code == 201
    data = res.json()
    assert data["gateway"] in ["razorpay", "upi"]