from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.db.session import Base, engine
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    
def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        lifespan=lifespan
    )
    
    application.include_router(health_router)
    application.include_router(payments_router)
    
    return application

app = create_app()