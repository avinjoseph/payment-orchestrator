from fastapi import APIRouter, Depends, Header, status

from app.api.dependencies import get_payment_service
from app.services.payment_services import (
    PaymentCreateRequest,
    PaymentResponse,
    PaymentService,
)

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    payment_service: PaymentService = Depends(get_payment_service)
    
):
    return await payment_service.process_payment(
        payload=payload,
        idempotency_key=idempotency_key
    )
    