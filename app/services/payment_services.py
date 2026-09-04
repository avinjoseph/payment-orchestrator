import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Transactions
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry
from app.models.payment import PaymentCreateRequest, PaymentResponse
from app.services.exceptions import (
    AllGatewaysExhaustedError,
    FailoverBudgetExceededError,
    NoHealthyGatewayError,
)
from app.services.failover import FailoverEngine
from app.services.health_monitor import GatewayHealthMonitor
from app.services.idempotency import IdempotencyManager
from app.services.router import SmartRouter
from app.services.state_machine import TransactionStateMachine


class PaymentService:
    def __init__(self, db: AsyncSession, redis: Redis, registry: GatewayRegistry | None = None):
        self.db = db
        self.redis = redis
        self.registry = registry or default_registry
        self.state_machine = TransactionStateMachine(db=self.db)
        self.idempotency = IdempotencyManager(redis=self.redis)
        self.health_monitor = GatewayHealthMonitor(redis=self.redis)
        self.router = SmartRouter(health_monitor=self.health_monitor, registry=self.registry)
        
    async def process_payment(self, payload: PaymentCreateRequest, idempotency_key: str) -> dict[str, Any]:
        async with self.idempotency.acquire_lock(idempotency_key):
            return await self._process_payment(payload, idempotency_key)

    async def _process_payment(self, payload: PaymentCreateRequest, idempotency_key: str) -> dict[str, Any]:
        # 1. Return cached payload immediately if already completed
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

        failover = FailoverEngine(
            redis=self.redis,
            state_machine=self.state_machine,
            registry=self.registry,
        )
        try:
            result = await failover.charge_with_failover(
                transaction_id=txn_id,
                amount=payload.amount,
                currency=payload.currency,
                method=payload.method,
                idempotency_key=idempotency_key,
            )
            gateway_name = result.gateway_name
            resp = result.response
        except (AllGatewaysExhaustedError, FailoverBudgetExceededError, NoHealthyGatewayError):
            current = txn.status
            if current == "routing":
                await self.state_machine.transition(
                    transaction_id=txn_id,
                    to_status="failed",
                    reason="No healthy gateway available",
                )
            elif current == "processing":
                await self.state_machine.transition(
                    transaction_id=txn_id,
                    to_status="failed",
                    reason="All gateway attempts failed",
                )
            await self.state_machine.transition(
                transaction_id=txn_id,
                to_status="failed_final",
                reason="Gateway failover exhausted",
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