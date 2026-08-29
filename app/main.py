from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.api.routes.webhooks import router as webhooks_router
from app.config import settings
from app.core.redis_client import close_redis, get_redis_client
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    redis = await get_redis_client()
    await redis.ping()
    
    yield
    
    await close_redis()
    await engine.dispose()
    
def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        lifespan=lifespan
    )
    
    register_error_handlers(application)    
    
    application.include_router(health_router)
    application.include_router(payments_router)
    application.include_router(webhooks_router)
    return application

app = create_app()