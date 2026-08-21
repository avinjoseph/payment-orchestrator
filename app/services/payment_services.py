import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionEvents, Transactions
from app.gateways.base import GatewayAdapter, GatewayResponse
from app.gateways.mock import MockGatewayAdapter
from app.models.payment import PaymentCreateRequest, PaymentResponse
from app.services.idempotency import IdempotencyManager
from app.services.state_machine import TransactionStateMachine


class PaymentService:
    def __init__(self, db: AsyncSession,redis:Redis, adapter: GatewayAdapter | None = None):
        self.db = db
        self.state_machine = TransactionStateMachine(db=self.db)
        self.idempotency = IdempotencyManager(redis=redis)
        self.adapter = adapter or MockGatewayAdapter()
        
    async def process_payment(self, payload: PaymentCreateRequest, idempotency_key: str) -> Transactions:
        
        # 1. Return cached payload immediately if already completed
        cached = await self.idempotency.get_cached_response(idempotency_key)
        if cached:
            return cached
        
        # 2. Acquire redis distribution lock
        async with self.idempotency.acquire_lock(idempotency_key):
            cached = await self.idempotency.get_cached_response(idempotency_key)
            if cached:
                return cached
            
        # 3. Create transaction record in 'created' state
        txn_id = uuid.uuid4()   
             
        # Initialize and persist the transaction record
        txn = Transactions(
            id = txn_id,
            idempotency_key=idempotency_key,
            amount= payload.amount,
            currency=payload.currency,
            status="created",
            customer_ref=payload.customer_ref,
            attempt_count=1

        )
        self.db.add(txn)
        
        init_event = TransactionEvents(
            transaction_id = txn_id,
            from_status = None,
            to_status="created",
            reason="Transaction record initialized"
        )
        
        self.db.add(init_event)
        await self.db.flush()
        
        # 4. State Machine Transition: created -> routing
        await self.state_machine.transition(
            transaction_id=txn_id,
            to_status="routing",
            reason="Evaluating gateway routing candidates"
        ) 
        
        # 5. State Machine Transition: routing -> processing
        gateway_name = getattr(self.adapter, "name", "mock_gateway")
        await self.state_machine.transition(
            transaction_id=txn_id,
            to_status="processing",
            gateway=gateway_name,
            reason=f"Dispatching charge to adapter: {gateway_name}"
        )
        
        # 6. Call Gateway
        
        resp = await self.adapter.charge(
            amount=payload.amount,
            currency=payload.currency,
            idempotency_key=idempotency_key
        )
        
        # 7. Final State Machine Transition: processing -> captured / failed
        
        
        if resp.success:
            txn = await self.state_machine.transition(
                transaction_id=txn_id,
                to_status=resp.status or "captured",
                gateway=gateway_name,
                gateway_txn_id=resp.gateway_txn_id,
                reason="Gateway authorization and capture successful",
                payload=resp.raw_payload
            )
        else:
            txn = await self.state_machine.transition(
                transaction_id=txn_id,
                to_status="failed",
                gateway=gateway_name,
                reason=resp.error_message or "Gateway charge failed",
                payload=resp.raw_payload
            )
            
        await self.db.commit()
        await self.db.refresh(txn)
        
        # 8. Cache response & return
        
        response_dto = PaymentResponse.model_validate(txn)
        response_dict = jsonable_encoder(response_dto)
        await self.idempotency.cache_response(idempotency_key, response_dict)
        
        return response_dict