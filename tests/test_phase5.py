# tests/test_phase5.py
import uuid

import pytest
from httpx import AsyncClient

from app.core.queue_client import get_queue_client
from app.db.models import Transactions
from app.db.session import AsyncSessionLocal
from app.gateways.base import SettlementRecord
from app.gateways.mock import MockGatewayAdapter
from app.gateways.registry import GatewayRegistry
from app.services.reconciliation import ReconiliationService
from app.workers.webhook_consumer import WebhookConsumerWorker


@pytest.mark.asyncio
async def test_webhook_ingestion_and_deduplication(async_client: AsyncClient):
    payload = {
        "event_id": f"evt_test_{uuid.uuid4().hex[:6]}",
        "event": "payment.captured",
        "gateway_txn_id": f"mock_tx_{uuid.uuid4().hex[:6]}",
        "amount": 5000,
    }

    # 1. Valid Signature -> 200 OK
    res1 = await async_client.post(
        "/webhooks/mock",
        json=payload,
        headers={"x-mock-signature": "valid_mock_signature"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "received"

    # 2. Duplicate Delivery -> 200 OK (deduplicated, status: duplicate_acknowledged)
    res2 = await async_client.post(
        "/webhooks/mock",
        json=payload,
        headers={"x-mock-signature": "valid_mock_signature"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate_acknowledged"

    # 3. Bad Signature -> 401 Unauthorized
    bad_payload = {
        "event_id": f"evt_bad_{uuid.uuid4().hex[:6]}",
        "event": "payment.captured",
        "gateway_txn_id": "mock_tx_bad",
        "amount": 5000,
    }
    res3 = await async_client.post(
        "/webhooks/mock",
        json=bad_payload,
        headers={"x-mock-signature": "bad_signature"},
    )
    assert res3.status_code == 401


@pytest.mark.asyncio
async def test_webhook_consumer_state_machine_transition():
    queue = await get_queue_client()
    gateway_txn_id = f"mock_tx_{uuid.uuid4().hex[:8]}"

    # Setup transaction in 'processing' state
    async with AsyncSessionLocal() as db:
        txn = Transactions(
            idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
            amount=10000,
            currency="USD",
            status="processing",
            gateway="mock",
            gateway_txn_id=gateway_txn_id,
        )
        db.add(txn)
        await db.commit()
        txn_id = txn.id

    # Simulate webhook worker processing message
    worker = WebhookConsumerWorker(queue=queue)
    async with AsyncSessionLocal() as db:
        await worker.process_single_message(
            db=db,
            message={
                "gateway": "mock",
                "payload": {
                    "event": "payment.captured",
                    "gateway_txn_id": gateway_txn_id,
                },
            },
        )

    # Verify state transition applied
    async with AsyncSessionLocal() as db:
        updated_txn = await db.get(Transactions, txn_id)
        assert updated_txn is not None
        assert updated_txn.status == "captured"


@pytest.mark.asyncio
async def test_reconciliation_detects_mismatches():
    mock_adapter = MockGatewayAdapter(name="mock")
    gateway_txn_id = f"rec_tx_{uuid.uuid4().hex[:8]}"

    # Inject mismatched settlement report into mock gateway
    mock_adapter.mock_settlement_records = [
        SettlementRecord(
            gateway_txn_id=gateway_txn_id,
            status="captured",
            amount=5000,
            currency="USD",
        ),
        SettlementRecord(
            gateway_txn_id="missing_remote_tx",
            status="captured",
            amount=3000,
            currency="USD",
        ),
    ]

    custom_registry = GatewayRegistry()
    custom_registry.register("mock", mock_adapter, {"USD"}, {"card"})

    async with AsyncSessionLocal() as db:
        txn = Transactions(
            idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
            amount=5000,
            currency="USD",
            status="failed",
            gateway="mock",
            gateway_txn_id=gateway_txn_id,
        )
        db.add(txn)
        await db.commit()

        reconciliation = ReconiliationService(db=db, registry=custom_registry)
        mismatches = await reconciliation.reconcile_gateway("mock")

        assert len(mismatches) == 2
        kinds = {m.kind for m in mismatches}
        assert "status_mismatch" in kinds
        assert "missing_locally" in kinds