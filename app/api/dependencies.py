from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.payment_services import PaymentService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session
        
async def get_payment_service(
    db: AsyncSession = Depends(get_db_session)
) -> PaymentService:
    return PaymentService(db=db)
