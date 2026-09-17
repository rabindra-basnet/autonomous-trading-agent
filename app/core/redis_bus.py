"""Distributed Event Bus using Upstash Redis Streams."""

import asyncio
import fnmatch
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

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
        self._handlers: dict[str, list[HandlerType]] = {}
        self._running = False
        self._listener_task = None
        self._block_ms = 1000
        self._reconnect_delay = 2.0

    async def connect(self):
        try:
            connect_kwargs: dict[str, Any] = {
                "decode_responses": True,
                # redis-py >= 8.1 defaults socket_timeout to 5s. That client-side
                # read timeout aborts the blocking XREADGROUP below even though
                # the server-side ``BLOCK`` already bounds every read, producing
                # spurious redis.exceptions.TimeoutError churn. Disable it and
                # rely on TCP keepalive plus reconnect-on-ConnectionError instead.
                "socket_timeout": None,
                "socket_keepalive": True,
                "health_check_interval": 30,
            }
            try:
                from redis.maint_notifications import MaintNotificationsConfig
            except ImportError:
                # redis-py < 8.1 has no maintenance-notification machinery.
                pass
            else:
                # This is a Redis 8.1 client feature that perturbs socket
                # timeouts on plain/OSS servers; leave it off for the stream bus.
                connect_kwargs["maint_notifications_config"] = MaintNotificationsConfig(enabled=False)

            self._redis = aioredis.from_url(settings.redis_url, **connect_kwargs)
            # Create consumer group if not exists
            try:
                await self._redis.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
            except ResponseError:
                logger.info("Consumer group %s already exists on stream %s.", self.group_name, self.stream_name)
            logger.info("Connected to Redis Streams event bus.")
        except Exception as e:
            logger.warning("Could not connect to Redis: %s", e)
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
            logger.error("Failed to publish to Redis stream: %s", e)

    async def _listener_loop(self):
        while self._running:
            if not self._redis:
                await self.connect()
                if not self._redis:
                    await asyncio.sleep(self._reconnect_delay)
                    continue
            try:
                entries = await self._redis.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_name: ">"},
                    count=50,
                    block=self._block_ms,
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
                                if fnmatch.fnmatch(topic, pattern):
                                    for h in handlers:
                                        asyncio.create_task(h(event))

                            # ACK message
                            await self._redis.xack(self.stream_name, self.group_name, msg_id)
            except asyncio.CancelledError:
                raise
            except (RedisTimeoutError, RedisConnectionError) as exc:
                logger.warning(
                    "Redis stream read interrupted (%s); reconnecting.",
                    exc.__class__.__name__,
                )
                await self._reconnect()
            except ResponseError as exc:
                logger.warning("Redis stream error: %s", exc)
                await asyncio.sleep(self._reconnect_delay)
            except Exception:
                logger.exception("Error in Redis listener loop")
                await asyncio.sleep(self._reconnect_delay)

    async def _reconnect(self):
        await asyncio.sleep(self._reconnect_delay)
        if not self._running:
            return
        stale, self._redis = self._redis, None
        if stale is not None:
            try:
                await stale.aclose()
            except Exception:
                logger.debug("Error closing stale Redis client", exc_info=True)
        await self.connect()

    async def start(self):
        self._running = True
        await self.connect()
        self._listener_task = asyncio.create_task(self._listener_loop())

    async def stop(self):
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None
