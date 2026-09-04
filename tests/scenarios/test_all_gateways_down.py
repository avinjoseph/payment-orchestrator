# tests/scenarios/test_all_gateways_down.py
import time

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Transactions
from app.db.session import AsyncSessionLocal


@pytest.mark.scenario
@respx.mock
async def test_all_gateways_exhausted_fails_fast(client: AsyncClient):
    # Mock all eligible gateways for INR + card
    respx.post("https://api.razorpay.com/v1/payments").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    respx.post("https://test.payu.in/merchant/postservice?form=2").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )

    start = time.perf_counter()
    idem_key = "scenario-all-down-key"
    res = await client.post(
        "/payments",
        json={
            "amount": 9900,
            "currency": "INR",
            "method": "card",
            "customer_ref": "cust_outage_user"
        },
        headers={"Idempotency-Key": idem_key}
    )
    elapsed = time.perf_counter() - start

    assert res.status_code == 503
    assert elapsed < 2.5

    # Transaction finalized in 'failed_final'
    async with AsyncSessionLocal() as db:
        stmt = select(Transactions).where(Transactions.idempotency_key == idem_key)
        txn = (await db.execute(stmt)).scalar_one_or_none()
        assert txn is not None
        assert txn.status == "failed_final"