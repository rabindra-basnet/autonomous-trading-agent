"""Distributed Event Bus using Upstash Redis Streams."""

import asyncio
import json
import logging
from typing import Callable, Coroutine, Dict, Any, List
import redis.asyncio as aioredis
from app.config import settings
from app.core.events import Event

logger = logging.getLogger("RedisEventBus")

HandlerType = Callable[[Event], Coroutine[Any, Any, None]]


class RedisStreamEventBus:
    def __init__(self, stream_name: str = "trading_events_stream", group_name: str = "trading_agent_group"):
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = f"consumer_{id(self)}"
        self._redis = None
        self._handlers: Dict[str, List[HandlerType]] = {}
        self._running = False
        self._listener_task = None

    async def connect(self):
        try:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            # Create consumer group if not exists
            try:
                await self._redis.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
            except Exception:
                # Group already exists
                pass
            logger.info("Connected to Redis Streams event bus.")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            self._redis = None

    def subscribe(self, topic_pattern: str, handler: HandlerType):
        if topic_pattern not in self._handlers:
            self._handlers[topic_pattern] = []
        if handler not in self._handlers[topic_pattern]:
            self._handlers[topic_pattern].append(handler)

    async def publish(self, event: Event):
        if not self._redis:
            return
        try:
            data = {
                "topic": event.topic,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "payload": json.dumps(event.payload),
            }
            await self._redis.xadd(self.stream_name, data)
        except Exception as e:
            logger.error(f"Failed to publish to Redis stream: {e}")

    async def _listener_loop(self):
        while self._running:
            if not self._redis:
                await asyncio.sleep(2.0)
                continue
            try:
                entries = await self._redis.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_name: ">"},
                    count=50,
                    block=1000,
                )
                if entries:
                    for stream, messages in entries:
                        for msg_id, raw_fields in messages:
                            topic = raw_fields.get("topic", "")
                            payload = json.loads(raw_fields.get("payload", "{}"))
                            event = Event(
                                topic=topic,
                                source=raw_fields.get("source", ""),
                                payload=payload,
                            )
                            # Dispatch to matching subscribers
                            for pattern, handlers in self._handlers.items():
                                import fnmatch
                                if fnmatch.fnmatch(topic, pattern):
                                    for h in handlers:
                                        asyncio.create_task(h(event))

                            # ACK message
                            await self._redis.xack(self.stream_name, self.group_name, msg_id)
            except Exception as e:
                logger.error(f"Error in Redis listener loop: {e}")
                await asyncio.sleep(1.0)

    async def start(self):
        self._running = True
        await self.connect()
        self._listener_task = asyncio.create_task(self._listener_loop())

    async def stop(self):
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
        if self._redis:
            await self._redis.close()
