from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionEvents, Transactions
from app.gateways.base import GatewayAdapter, GatewayResponse
from app.gateways.mock import MockGatewayAdapter
from app.models.payment import PaymentCreateRequest, PaymentResponse


class PaymentService:
    def __init__(self, db: AsyncSession, adapter: GatewayAdapter | None = None):
        self.db = db
        self.adapter = adapter or MockGatewayAdapter()
        
    async def process_payment(self, payload: PaymentCreateRequest, idempotency_key: str) -> Transactions:
        # Initialize and persist the transaction record
        txn = Transactions(
            idempotency_key=idempotency_key,
            amount= payload.amount,
            currency=payload.currency,
            status="processing",
            gateway=getattr(self.adapter,"name","unkown_gateway"),
            customer_ref=payload.customer_ref,
            attempt_count=1

        )
        self.db.add(txn)
        await self.db.flush()
        
        # Journal the initial transition event
        
        init_event = TransactionEvents(
            transaction_id = txn.id,
            from_status = None,
            to_status="processing",
            gateway=txn.gateway,
            reason="Transaction initiated"
        )
        
        self.db.add(init_event)
        
        
        # Invoke gateway adapter
        
        resp = await self.adapter.charge(
            amount=payload.amount,
            currency=payload.currency,
            idempotency_key=idempotency_key
        )
        
        # Update transaction state based on response
        
        if resp.success:
            txn.status = resp.status or "captured"
            txn.gateway_txn_id = resp.gateway_txn_id
            
            event = TransactionEvents(
                transaction_id=txn.id,
                from_status="processing",
                to_status=txn.status,
                gateway=txn.gateway,
                reason="Payment charge sucessful",
                payload= resp.raw_payload
            )   
            
        else:
            
            txn.status = "failed"
            event = TransactionEvents(
                            transaction_id=txn.id,
                            from_status="processing",
                            to_status="failed",
                            gateway=txn.gateway,
                            reason= resp.error_message or "Charge request failed",
                            payload= resp.raw_payload
                        ) 
        
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(txn)
        
        return txn