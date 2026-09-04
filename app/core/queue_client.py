import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from redis.asyncio import Redis

from app.core.redis_client import get_redis_client

WEBHOOK_STREAM_NAME = "stream:webhook_events"
WEBHOOK_GROUP_NAME = "group:webhook_workers"

class QueueClient:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish(self, stream_name: str, message: dict) -> str:
        serialized: dict[str, str] = {"data": json.dumps(message)}
        msg_id = await self.redis.xadd(stream_name, cast(dict[str, Any], serialized))  # type: ignore[arg-type]
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id

    async def ensure_consumer_group(self, stream_name: str, group_name: str) -> None:
        try:
            await self.redis.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except Exception as e:
            # BUSYGROUP Consumer Group name already exists
            if "BUSYGROUP" not in str(e):
                raise
            
    async def consume(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 2000
    ) -> AsyncGenerator[tuple[str, dict], None]:
        await self.ensure_consumer_group(stream_name, group_name)
        while True:
            entries = cast(list[tuple[str | bytes, list[tuple[str | bytes, dict[str, Any]]]]], await self.redis.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_name: ">"},
                count=count,
                block=block_ms
            ))
            if not entries:
                continue

            for _, messages in entries:
                for msg_id, raw_data in messages:
                    raw_message = cast(dict[str, Any], raw_data)
                    raw_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    payload = json.loads(raw_message["data"])
                    yield raw_id, payload

    async def ack(self, stream_name: str, group_name: str, msg_id: str) -> None:
        await self.redis.xack(stream_name, group_name, msg_id)
        

async def get_queue_client() -> QueueClient:
    redis = await get_redis_client()
    return QueueClient(redis=redis)