import time
import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionEvents, Transactions
from app.gateways.base import GatewayAdapter, GatewayResponse, TransientGatewayError
from app.gateways.mock import MockGatewayAdapter
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry
from app.models.payment import PaymentCreateRequest, PaymentResponse
from app.services.health_monitor import GatewayHealthMonitor
from app.services.idempotency import IdempotencyManager
from app.services.router import SmartRouter
from app.services.state_machine import TransactionStateMachine


class PaymentService:
    def __init__(self, db: AsyncSession,redis:Redis, registry: GatewayAdapter | None = None):
        self.db = db
        self.redis = redis
        self.registry = registry or default_registry
        self.state_machine = TransactionStateMachine(db=self.db)
        self.idempotency = IdempotencyManager(redis=self.redis)
        self.health_monitor = GatewayHealthMonitor(redis=self.redis)
        self.router = SmartRouter(health_monitor=self.health_monitor, registry=self.registry)
        
    async def process_payment(self, payload: PaymentCreateRequest, idempotency_key: str) -> dict[str, Any]:
        
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
        await self.db.flush()
        
        # 1. State Machine: created -> routing
        await self.state_machine.transition(
            transaction_id=txn_id,
            to_status="routing",
            reason="Routing through dynamic scorecard"
        )

        # 2. Dynamic Router Selection
        gateway_name = await self.router.select_gateway(
            method=payload.method,
            currency=payload.currency
        )
        
        adapter = self.registry.get_adapter(gateway_name)
        
        # 3. State Machine: routing -> processing
        await self.state_machine.transition(
            transaction_id=txn_id,
            to_status="processing",
            gateway=gateway_name,
            reason=f"Selected healthiest gateway: {gateway_name}"
        )
        
        # 4. Invoke Selected Gateway & Record Health Signal
        start_time = time.perf_counter()
        try:
            resp: GatewayResponse = await adapter.charge(
                amount=payload.amount,
                currency=payload.currency,
                method=payload.method,
                idempotency_key=idempotency_key
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            await self.health_monitor.record_outcome(
                gateway=gateway_name,
                success=(resp.status in ["success", "pending"]),
                latency_ms=elapsed_ms
            )
        except TransientGatewayError as ex:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            await self.health_monitor.record_outcome(
                gateway=gateway_name,
                success=False,
                latency_ms=elapsed_ms
            )
            await self.state_machine.transition(
                transaction_id=txn_id,
                to_status="failed",
                gateway=gateway_name,
                reason=f"Gateway transient error: {ex.message}"
            )
            await self.db.commit()
            raise
        
        
        # 5. Map Gateway response to State Machine state
        status_map = {
            "success": "captured",
            "pending": "processing",
            "declined": "failed",
            "error": "failed"
        }
        target_status = status_map.get(resp.status, "failed")

        txn = await self.state_machine.transition(
            transaction_id=txn_id,
            to_status=target_status,
            gateway=gateway_name,
            gateway_txn_id=resp.gateway_txn_id,
            reason=f"Adapter outcome: {resp.status}",
            payload=resp.raw
        )

        await self.db.commit()
        await self.db.refresh(txn)

        response_dto = PaymentResponse.model_validate(txn)
        response_dict = jsonable_encoder(response_dto)
        await self.idempotency.cache_response(idempotency_key, response_dict)

        return response_dict