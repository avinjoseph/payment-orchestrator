from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreateRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in minor currency units (e.g. cents or paise)")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code (e.g. USD, EUR, INR)")
    method: str = Field(..., description="Payment method: card, upi, netbanking, bank_transfer, wallet)")
    customer_ref: str | None = Field(None, description="Client unique customer reference")
    
class PaymentResponse(BaseModel):
    id: UUID
    idempotency_key: str
    amount: int
    currency: str
    status: str
    gateway: str | None = None
    gateway_txn_id: str | None = None
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True)
    
class TransactionEventResponse(BaseModel):
    id:int
    from_status:str | None
    to_status:str
    gateway: str | None
    reason: str | None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    
class PaymentDetailResponse(PaymentResponse):
    events: list[TransactionEventResponse] = []