from fastapi import APIRouter, Header, Depends, status
from app.services.payment_services import PaymentCreateRequest, PaymentResponse, PaymentService
from app.api.dependencies import get_payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    payment_service: PaymentService = Depends(get_payment_service)
    
):
    txn = await payment_service.process_payment(
        payload=payload,
        idempotency_key=idempotency_key
    )
    
    return txn