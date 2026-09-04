import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionEvents, Transactions
from app.services.exceptions import IllegalTransitionError, TransactionNotFoundException

logger = structlog.get_logger(__name__)
class TransactionStateMachine:
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {  # noqa: RUF012
        "created": {"routing", "processing", "failed"},
        "routing": {"processing", "failed"},
        "processing": {"processing","authorized", "captured", "failed", "failed_final"},
        "authorized": {"captured", "voided", "failed"},
        "captured": {"settled", "refunded"},
        "settled": {"refunded"},
        "failed": {"failed_final", "routing", "processing"},
        "refunded": set(),
        "voided": set(),
        "failed_final": set(),
    }
    
    def __init__(self, db: AsyncSession):
         self.db = db
    
    def is_valid_transaction(self, from_status: str, to_status: str) -> bool:
        return to_status in self.ALLOWED_TRANSITIONS.get(from_status, set())
    
    async def transition(
        self,
        transaction_id: uuid.UUID,
        to_status: str,
        gateway: str | None = None,
        gateway_txn_id: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Transactions:
        stmt = (
            select(Transactions)
            .where(Transactions.id == transaction_id)
            .with_for_update()
        )
        
        result = await self.db.execute(stmt)
        txn = result.scalar_one_or_none()

        if not txn:
            raise TransactionNotFoundException(transaction_id)
        
        logger.info(
            "transaction_state_transition",
            transaction_id=str(txn.id),
            to_status=to_status,
            gateway=gateway or txn.gateway,
            reason=reason
        )
        
        if not self.is_valid_transaction(txn.status, to_status):
            raise IllegalTransitionError(
                current_status=txn.status,
                target_status=to_status,
                transaction_id=txn.id,
            )
            
        from_status = txn.status
        txn.status = to_status
        if gateway is not None:
            txn.gateway = gateway
        if gateway_txn_id is not None:
            txn.gateway_txn_id = gateway_txn_id
        
        event = TransactionEvents(
            transaction_id=txn.id,
            from_status=from_status,
            to_status=to_status,
            gateway=gateway or txn.gateway,
            reason=reason,
            payload=payload,
        )
        self.db.add(event)
        await self.db.flush()  # Ensure the event is persisted before returning the transaction
        return txn
    
    