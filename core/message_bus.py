"""
CareerPilot — Async Message Bus
================================
Lightweight, in-process pub/sub message bus for inter-agent communication.
Backed by asyncio.Queue. Upgrade path: swap implementation for Redis Streams
or RabbitMQ without changing agent code.

Topics
------
  jobs         — new / updated job postings
  profiles     — LinkedIn / email profile data
  predictions  — fit scores and recommendations
  commands     — high-level goals from the user / Commander
  events       — lifecycle events (applied, interviewed, offered, rejected)

Usage
-----
>>> bus = MessageBus()
>>> await bus.subscribe("jobs", handler)
>>> await bus.publish(AgentMessage(topic="jobs", ...))
"""
from __future__ import annotations

import io
import sys

# Force UTF-8 on Windows (CP1252 consoles crash on Unicode log output)
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer") and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import itertools
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import structlog

from models.schemas import AgentMessage, MessagePriority, MessageType

logger = structlog.get_logger(__name__)

# Type alias for async message handlers
MessageHandler = Callable[[AgentMessage], Awaitable[None]]

# Valid bus topics
TOPICS = frozenset({"jobs", "profiles", "predictions", "commands", "events"})


@dataclass
class Subscription:
    """A single topic → handler binding."""

    topic: str
    handler: MessageHandler
    subscriber_id: str
    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class MessageBus:
    """
    Async publish/subscribe message bus.

    Guarantees
    ----------
    - Messages are delivered in priority order (HIGH > NORMAL > LOW).
    - Each subscriber receives its own copy of the message.
    - Handlers that raise exceptions are logged and do NOT crash the bus.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        # 3-tuple: (priority_int, seq, message) — seq breaks ties so AgentMessage
        # objects are never compared directly (they don't support __lt__).
        self._queue: asyncio.PriorityQueue[tuple[int, int, AgentMessage]] = (
            asyncio.PriorityQueue()
        )
        self._seq = itertools.count()   # monotonic tiebreaker
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._message_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background dispatch loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop(), name="bus-dispatcher")
        logger.info("message_bus.started")

    async def stop(self) -> None:
        """Gracefully shut down the bus."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("message_bus.stopped", total_messages=self._message_count)

    # ── Pub/Sub API ───────────────────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        subscriber_id: str,
    ) -> Subscription:
        """
        Register *handler* to receive messages on *topic*.

        Parameters
        ----------
        topic:         One of the valid TOPICS constants.
        handler:       Async callable that accepts an AgentMessage.
        subscriber_id: Human-readable identifier of the subscribing agent.

        Returns
        -------
        Subscription object (store it to unsubscribe later).
        """
        if topic not in TOPICS:
            raise ValueError(f"Unknown topic '{topic}'. Valid: {sorted(TOPICS)}")
        sub = Subscription(topic=topic, handler=handler, subscriber_id=subscriber_id)
        self._subscriptions[topic].append(sub)
        logger.debug(
            "bus.subscribed", topic=topic, subscriber=subscriber_id, sub_id=sub.subscription_id
        )
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a previously registered subscription."""
        subs = self._subscriptions.get(subscription.topic, [])
        self._subscriptions[subscription.topic] = [
            s for s in subs if s.subscription_id != subscription.subscription_id
        ]

    async def publish(self, message: AgentMessage) -> None:
        """
        Enqueue a message for async delivery.

        Priority mapping: HIGH=0, NORMAL=1, LOW=2 (lower int = higher priority).
        The sequence counter guarantees AgentMessage objects are never compared
        directly by heapq (which would raise TypeError on Python 3.13+).
        """
        priority_int = {"HIGH": 0, "NORMAL": 1, "LOW": 2}[message.priority.value]
        await self._queue.put((priority_int, next(self._seq), message))
        logger.debug(
            "bus.published",
            topic=message.topic,
            sender=message.sender,
            msg_type=message.type.value,
            msg_id=message.id,
        )

    async def publish_sync(self, message: AgentMessage) -> None:
        """Publish and immediately await all handlers (useful for testing)."""
        await self._deliver(message)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        """Background loop that drains the priority queue and delivers messages."""
        while self._running:
            try:
                _, _seq, message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._deliver(message)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("bus.dispatch_error", error=str(exc))

    async def _deliver(self, message: AgentMessage) -> None:
        """Fan-out a message to all subscribers of its topic."""
        subscribers = self._subscriptions.get(message.topic, [])
        self._message_count += 1

        if not subscribers:
            logger.warning("bus.no_subscribers", topic=message.topic, msg_id=message.id)
            return

        for sub in subscribers:
            try:
                await sub.handler(message)
            except Exception as exc:
                logger.exception(
                    "bus.handler_error",
                    subscriber=sub.subscriber_id,
                    topic=message.topic,
                    error=str(exc),
                )

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return bus runtime statistics."""
        return {
            "running": self._running,
            "total_messages_dispatched": self._message_count,
            "queue_size": self._queue.qsize(),
            "subscriptions": {
                topic: [s.subscriber_id for s in subs]
                for topic, subs in self._subscriptions.items()
            },
        }


# Module-level singleton — shared across all agents
_bus: MessageBus | None = None


def get_bus() -> MessageBus:
    """Return (or lazily create) the global MessageBus instance."""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
