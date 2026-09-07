# tests/test_phase8.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_key_authentication_enforcement(client: AsyncClient):
    # 1. Unauthenticated -> 401 Unauthorized
    res_no_auth = await client.post(
        "/payments",
        json={"amount": 1000, "currency": "USD", "method": "card"},
        headers={"Idempotency-Key": "auth-test-none"},
    )
    assert res_no_auth.status_code == 401

    # 2. Invalid Token -> 401 Unauthorized
    res_bad_auth = await client.post(
        "/payments",
        json={"amount": 1000, "currency": "USD", "method": "card"},
        headers={
            "Idempotency-Key": "auth-test-bad",
            "Authorization": "Bearer invalid_secret_token",
        },
    )
    assert res_bad_auth.status_code == 401


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    res = await client.get("/live")
    assert res.status_code == 200
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Strict-Transport-Security" in res.headers


@pytest.mark.asyncio
async def test_liveness_and_readiness_endpoints(client: AsyncClient):
    # Liveness check
    live_res = await client.get("/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "live"

    # Readiness check
    ready_res = await client.get("/ready")
    assert ready_res.status_code == 200
    data = ready_res.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"