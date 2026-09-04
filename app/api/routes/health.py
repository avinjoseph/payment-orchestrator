from fastapi import APIRouter, status

from app.config import settings

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