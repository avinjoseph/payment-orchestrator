# tests/conftest.py
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal, Base, engine
from app.main import app


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialize_test_database():
    """Create all tables once per test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_env_between_tests():
    """Ensure database schema is up-to-date and wipe state cleanly before every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    redis = get_redis_client()
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE transaction_events, transactions, inbound_webhooks, reconciliation_mismatches "
                "RESTART IDENTITY CASCADE;"
            )
        )
        await session.commit()

    yield

    redis = get_redis_client()
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()



@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def async_client(client: AsyncClient):
    yield client