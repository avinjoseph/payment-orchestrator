from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.payment_services import PaymentService
from redis.asyncio import Redis
from app.core.redis_client import get_redis_client

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session
        
async def get_payment_service(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
) -> PaymentService:
    return PaymentService(db=db, redis=redis)
