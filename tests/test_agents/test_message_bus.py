"""Tests for the MessageBus."""

from __future__ import annotations

import asyncio
import pytest
from models.schemas import AgentMessage, MessagePriority, MessageType


class TestMessageBus:
    """Unit tests for core/message_bus.py"""

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, bus):
        """A subscribed handler should receive published messages."""
        received = []

        async def handler(msg: AgentMessage) -> None:
            received.append(msg)

        bus.subscribe("jobs", handler, "test-agent")
        msg = AgentMessage(
            sender="tracker", topic="jobs",
            type=MessageType.EVENT,
            payload={"type": "new_jobs_found", "count": 3},
        )
        await bus.publish_sync(msg)
        assert len(received) == 1
        assert received[0].payload["count"] == 3

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Handler should not receive messages after unsubscribing."""
        received = []

        async def handler(msg: AgentMessage) -> None:
            received.append(msg)

        sub = bus.subscribe("jobs", handler, "test-agent")
        bus.unsubscribe(sub)

        msg = AgentMessage(
            sender="tracker", topic="jobs",
            type=MessageType.EVENT, payload={},
        )
        await bus.publish_sync(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_invalid_topic_raises(self, bus):
        """Subscribing to an unknown topic should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown topic"):
            bus.subscribe("invalid_topic", lambda m: None, "test")

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_bus(self, bus):
        """A failing handler should not prevent other handlers from running."""
        results = []

        async def bad_handler(msg: AgentMessage) -> None:
            raise RuntimeError("Intentional error")

        async def good_handler(msg: AgentMessage) -> None:
            results.append(msg)

        bus.subscribe("events", bad_handler, "bad-agent")
        bus.subscribe("events", good_handler, "good-agent")

        msg = AgentMessage(sender="x", topic="events", type=MessageType.EVENT, payload={})
        await bus.publish_sync(msg)

        # Good handler should still have received it
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_stats(self, bus):
        """Bus stats should report correct subscription info."""
        async def noop(m: AgentMessage) -> None:
            pass

        bus.subscribe("jobs", noop, "agent-a")
        stats = bus.stats()
        assert "jobs" in stats["subscriptions"]
        assert "agent-a" in stats["subscriptions"]["jobs"]
