from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.error_handlers import register_error_handlers
from app.api.middleware import (
    RequestCorrelationMiddleware,
    SecurityHeadersMiddleware,
)
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.api.routes.webhooks import router as webhooks_router
from app.config import settings
from app.core.logging import setup_logging
from app.core.redis_client import close_redis, get_redis_client
from app.db.session import Base, engine

setup_logging()


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
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=None
    )
    
    # Middleware
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestCorrelationMiddleware)
    
    if settings.CORS_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        )
    # Metrics endpoint
    Instrumentator().instrument(application).expose(application, endpoint="/metrics")
    
    register_error_handlers(application)    
    
    application.include_router(health_router)
    application.include_router(payments_router)
    application.include_router(webhooks_router)
    return application

app = create_app()