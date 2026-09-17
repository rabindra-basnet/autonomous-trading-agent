"""Asynchronous, high-throughput Event Bus supporting pattern matching and decoupled dispatch."""

import asyncio
import fnmatch
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.core.events import Event

logger = logging.getLogger("EventBus")

HandlerType = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self, max_queue_size: int = 10000):
        self._subscribers: dict[str, list[HandlerType]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None

    def subscribe(self, topic_pattern: str, handler: HandlerType) -> None:
        """Subscribe an async handler to a topic or glob pattern (e.g. 'market.*')."""
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
        if handler not in self._subscribers[topic_pattern]:
            self._subscribers[topic_pattern].append(handler)
            logger.debug(f"Subscribed handler {handler.__name__} to pattern '{topic_pattern}'")

    def unsubscribe(self, topic_pattern: str, handler: HandlerType) -> None:
        """Unsubscribe an async handler."""
        if topic_pattern in self._subscribers and handler in self._subscribers[topic_pattern]:
            self._subscribers[topic_pattern].remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to the queue for asynchronous dispatch."""
        try:
            await self._queue.put(event)
        except asyncio.QueueFull:
            logger.warning(f"Event bus queue full! Dropping event on topic {event.topic}")

    async def publish_immediate(self, event: Event) -> None:
        """Synchronously route the event to all matching subscribers without queuing."""
        await self._dispatch_event(event)

    async def _dispatch_event(self, event: Event) -> None:
        tasks = []
        for pattern, handlers in self._subscribers.items():
            if fnmatch.fnmatch(event.topic, pattern):
                for handler in handlers:
                    tasks.append(self._safe_call_handler(handler, event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call_handler(self, handler: HandlerType, event: Event) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.exception(f"Error in event handler {handler.__name__} for topic {event.topic}: {e}")

    async def _worker_loop(self) -> None:
        logger.info("EventBus worker loop started.")
        while self._running:
            event = await self._queue.get()
            try:
                await self._dispatch_event(event)
            except Exception:
                logger.exception("Unexpected error in EventBus dispatch")
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self._running:
            self._running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("EventBus stopped.")
