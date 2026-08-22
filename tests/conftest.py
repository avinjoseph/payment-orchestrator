# tests/conftest.py
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from app.main import app
from app.db.session import AsyncSessionLocal, engine
from app.core.redis_client import get_redis_client, close_redis


@pytest_asyncio.fixture(autouse=True)
async def cleanup_env_between_tests():
    """Wipes Redis and Postgres tables before each test."""
    redis = await get_redis_client()
    await redis.flushdb()
    
    async with AsyncSessionLocal() as session:
        await session.execute(text("TRUNCATE TABLE transaction_events, transactions RESTART IDENTITY CASCADE;"))
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