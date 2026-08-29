# tests/conftest.py
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.redis_client import close_redis, get_redis_client
from app.db.session import AsyncSessionLocal, Base, engine
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def cleanup_env_between_tests():
    """Ensures tables exist and wipes test data between tests."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    redis = await get_redis_client()
    await redis.flushdb()
    
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE transaction_events, transactions, inbound_webhooks, reconciliation_mismatches "
                "RESTART IDENTITY CASCADE;"
            )
        )
        await session.commit()
        
    yield

    await redis.flushdb()
    await close_redis()
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client