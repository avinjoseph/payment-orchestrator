# tests/test_phase2.py
import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@respx.mock
async def test_idempotency_and_state_machine():
    respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=httpx.Response(200, json={
            "id": "pi_phase2_mock_1",
            "status": "succeeded"
        })
    )
    respx.post("https://api.razorpay.com/v1/payments").mock(
        return_value=httpx.Response(200, json={
            "id": "pay_phase2_mock_1",
            "status": "captured"
        })
    )

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

        # Second request: Idempotent return of cached transaction
        res2 = await client.post("/payments", json=payload, headers=headers)
        assert res2.status_code == 201
        data2 = res2.json()
        assert data1["id"] == data2["id"]