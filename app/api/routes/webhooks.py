import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.queue_client import WEBHOOK_STREAM_NAME, QueueClient, get_queue_client
from app.db.models import InboundWebhook
from app.gateways.registry import GatewayRegistry
from app.gateways.registry import registry as default_registry

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/{gateway}", status_code=status.HTTP_200_OK)
async def ingest_webhook(
    gateway: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    queue: QueueClient = Depends(get_queue_client),
    registry: GatewayRegistry = Depends(lambda: default_registry),
):
    try:
        adapter = registry.get_adapter(gateway)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway '{gateway}' not recognized",
        ) from err
    
    # 1. Read exact raw bytes for cryptographic signature verification
    raw_body = await request.body()
    headers_dict = dict(request.headers)
    
    # 2. Verify Signature
    if not adapter.verify_webhook(raw_body, headers_dict):
        logger.warning("invalid_webhook_signature", gateway=gateway)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON") from err

    # 3. Extract unique Event ID
    event_id = adapter.extract_event_id(payload)

    # 4. Durable Database Deduplication
    inbound_record = InboundWebhook(
        gateway=gateway,
        gateway_event_id=event_id,
        payload=payload,
    )
    db.add(inbound_record)
    
    try:
        await db.commit()
    except IntegrityError:
        # Duplicate delivery from gateway: acknowledge 200 OK immediately without re-queueing
        await db.rollback()
        logger.info("duplicate_webhook_ignored", gateway=gateway, event_id=event_id)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "duplicate_acknowledged"})

    # 5. Hand off to async queue
    await queue.publish(
        stream_name=WEBHOOK_STREAM_NAME,
        message={
            "gateway": gateway,
            "event_id": event_id,
            "payload": payload,
        }
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "received"})