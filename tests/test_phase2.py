# tests/test_phase2.py
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_idempotency_and_state_machine():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        idempotency_key = "phase2-integration-test-01"
        payload = {
            "amount": 9990,
            "currency": "USD",
            "method": "card",
            "customer_ref": "cust_phase2"
        }
        headers = {"Idempotency-Key": idempotency_key}

        # First request: Creates and captures transaction
        res1 = await client.post("/payments", json=payload, headers=headers)
        assert res1.status_code == 201
        data1 = res1.json()
        assert data1["status"] == "captured"
        assert data1["idempotency_key"] == idempotency_key

        # Second request with identical key: Returns cached response instantly
        res2 = await client.post("/payments", json=payload, headers=headers)
        assert res2.status_code == 201
        data2 = res2.json()
        assert data1["id"] == data2["id"]
        assert data1["created_at"] == data2["created_at"]