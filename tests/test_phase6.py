# tests/test_phase6.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_metrics_endpoint_exposed(async_client: AsyncClient):
    res = await async_client.get("/metrics")
    assert res.status_code == 200
    assert "payment_requests_total" in res.text
    assert "payment_latency_seconds" in res.text
    assert "circuit_breaker_state" in res.text
    assert "failover_events_total" in res.text

@pytest.mark.asyncio
async def test_correlation_id_propagated(async_client: AsyncClient):
    custom_request_id = "test-corr-id-9988"
    res = await async_client.get("/health", headers={"X-Request-ID": custom_request_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_request_id