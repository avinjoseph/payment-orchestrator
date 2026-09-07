from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.config import settings
from app.core.redis_client import get_redis_client

router = APIRouter(tags=["Health"])

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return{
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "gateways": {
            "mock_gateway": "online"
        }
    }
    
    
@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Process level check. Confirms the event loop is responsive."""
    return {"status": "live", "version": settings.VERSION}

@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
) -> dict[str, str]:
    """Dependency check. Confirms PostgreSQL and Redis connections are functional."""
    # Check Database
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {str(e)}",
        ) from e

    # Check Redis
    try:
        await redis.ping()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unreachable: {str(e)}",
        ) from e

    return {
        "status": "ready",
        "database": "connected",
        "redis": "connected",
        "environment": settings.ENVIRONMENT,
    }