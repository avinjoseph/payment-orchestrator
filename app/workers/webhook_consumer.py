# app/workers/webhook_consumer.py
import asyncio
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models import Transactions
from app.core.queue_client import QueueClient, get_queue_client, WEBHOOK_STREAM_NAME, WEBHOOK_GROUP_NAME
from app.gateways.registry import GatewayRegistry, registry as default_registry
from app.services.state_machine import TransactionStateMachine
from app.services.exceptions import IllegalTransitionError

logger = structlog.get_logger(__name__)


class WebhookConsumerWorker:
    def __init__(self, queue: QueueClient, registry: GatewayRegistry | None = None):
        self.queue = queue
        self.registry = registry or default_registry

    async def process_single_message(self, db: AsyncSession, message: dict) -> None:
        gateway = message["gateway"]
        payload = message["payload"]
        adapter = self.registry.get_adapter(gateway)

        event = adapter.map_webhook_to_status(payload)
        if event.normalized_status == "ignored":
            return

        # Query transaction by gateway_txn_id with retries for out-of-order arrival
        stmt = select(Transactions).where(Transactions.gateway_txn_id == event.gateway_txn_id)
        res = await db.execute(stmt)
        txn = res.scalar_one_or_none()

        if txn is None:
            logger.warning("transaction_not_found_for_webhook", gateway_txn_id=event.gateway_txn_id)
            return

        state_machine = TransactionStateMachine(db=db)
        status_map = {
            "success": "captured",
            "declined": "failed",
            "refunded": "refunded",
            "pending": "processing",
        }
        target_status = status_map.get(event.normalized_status, "failed")

        try:
            await state_machine.transition(
                transaction_id=txn.id,
                to_status=target_status,
                gateway=gateway,
                reason=f"Webhook event applied: {event.event_type}",
                payload=payload,
            )
            await db.commit()
            logger.info("webhook_transition_applied", txn_id=str(txn.id), target_status=target_status)
        except IllegalTransitionError as e:
            # Out-of-order delivery (e.g. webhook for settled arrived after manual refund)
            logger.info("webhook_transition_skipped", reason=str(e))
            await db.rollback()

    async def run(self, max_messages: int | None = None) -> None:
        processed = 0
        consumer_name = "worker-node-1"

        async for msg_id, payload in self.queue.consume(
            stream_name=WEBHOOK_STREAM_NAME,
            group_name=WEBHOOK_GROUP_NAME,
            consumer_name=consumer_name,
        ):
            async with AsyncSessionLocal() as db:
                try:
                    await self.process_single_message(db, payload)
                    await self.queue.ack(WEBHOOK_STREAM_NAME, WEBHOOK_GROUP_NAME, msg_id)
                except Exception as ex:
                    logger.exception("webhook_consumer_error", error=str(ex))

            processed += 1
            if max_messages and processed >= max_messages:
                break