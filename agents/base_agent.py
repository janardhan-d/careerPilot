"""
CareerPilot — BaseAgent
========================
Abstract base class for all CareerPilot agents.

Provides:
  - Lifecycle: start() / stop()
  - Message handling: subscribe to bus, dispatch to handle_message()
  - Tool invocation: use_tool() proxy to the shared registry
  - Memory: working + long-term via Memory class
  - LLM: ask_llm() with OpenAI / Ollama fallback

All concrete agents must implement:
  - agent_id: str  (class attribute)
  - subscribed_topics: list[str]
  - handle_message(msg) -> None
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

import structlog

from core.config import settings
from core.memory import Memory
from core.message_bus import MessageBus, Subscription, get_bus
from core.tool_registry import registry
from models.schemas import AgentMessage, MessagePriority, MessageType

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all CareerPilot agents.

    Subclasses must define:
      - `agent_id`           — unique string identifier
      - `subscribed_topics`  — list of message bus topics to subscribe to
      - `handle_message()`   — async method invoked for each received message
    """

    agent_id: str = "base"
    subscribed_topics: list[str] = []

    def __init__(self, bus: MessageBus | None = None) -> None:
        self._bus = bus or get_bus()
        self._memory = Memory(agent_id=self.agent_id)
        self._subscriptions: list[Subscription] = []
        self._running = False
        self._log = structlog.get_logger(self.__class__.__name__)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe to topics and begin processing messages."""
        if self._running:
            return
        self._running = True

        for topic in self.subscribed_topics:
            sub = self._bus.subscribe(
                topic=topic,
                handler=self._safe_handle,
                subscriber_id=self.agent_id,
            )
            self._subscriptions.append(sub)

        await self.on_start()
        self._log.info("agent.started", agent=self.agent_id, topics=self.subscribed_topics)

    async def stop(self) -> None:
        """Unsubscribe and clean up."""
        self._running = False
        for sub in self._subscriptions:
            self._bus.unsubscribe(sub)
        self._subscriptions.clear()
        await self.on_stop()
        self._log.info("agent.stopped", agent=self.agent_id)

    # ── Hooks (override as needed) ─────────────────────────────────────────────

    async def on_start(self) -> None:
        """Hook called after the agent has subscribed. Override to init resources."""

    async def on_stop(self) -> None:
        """Hook called before the agent shuts down. Override to release resources."""

    # ── Message handling ───────────────────────────────────────────────────────

    async def _safe_handle(self, message: AgentMessage) -> None:
        """Wrap handle_message() to log exceptions without crashing the bus."""
        try:
            await self.handle_message(message)
        except Exception as exc:
            self._log.exception(
                "agent.handle_error",
                agent=self.agent_id,
                msg_id=message.id,
                error=str(exc),
            )
            # Emit an error message back to the bus
            await self.emit(
                topic=message.topic,
                msg_type=MessageType.ERROR,
                payload={"original_msg_id": message.id, "error": str(exc)},
                correlation_id=message.id,
            )

    @abstractmethod
    async def handle_message(self, message: AgentMessage) -> None:
        """Process an incoming message. Must be implemented by subclasses."""

    # ── Emit helpers ───────────────────────────────────────────────────────────

    async def emit(
        self,
        topic: str,
        msg_type: MessageType,
        payload: dict[str, Any],
        recipient: str | None = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        correlation_id: str | None = None,
    ) -> None:
        """Publish a message to the bus from this agent."""
        message = AgentMessage(
            sender=self.agent_id,
            recipient=recipient,
            topic=topic,
            type=msg_type,
            priority=priority,
            payload=payload,
            correlation_id=correlation_id,
        )
        await self._bus.publish(message)
        self._log.debug(
            "agent.emitted",
            agent=self.agent_id,
            topic=topic,
            type=msg_type.value,
            msg_id=message.id,
        )

    async def emit_event(self, topic: str, payload: dict[str, Any]) -> None:
        """Shortcut to emit a broadcast EVENT message."""
        await self.emit(topic=topic, msg_type=MessageType.EVENT, payload=payload)

    async def reply(self, original: AgentMessage, payload: dict[str, Any]) -> None:
        """Send a RESULT reply correlated to an incoming message."""
        msg = original.reply(sender=self.agent_id, payload=payload)
        await self._bus.publish(msg)

    # ── Tool invocation ────────────────────────────────────────────────────────

    async def use_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """
        Invoke a registered tool by name.

        Wraps registry.invoke() with agent-level logging.
        """
        self._log.info("agent.using_tool", agent=self.agent_id, tool=tool_name)
        return await registry.invoke(tool_name, payload=kwargs)

    def list_tools(self, tags: list[str] | None = None) -> list[dict[str, Any]]:
        """Return available tools, optionally filtered by tags."""
        return registry.list_tools(tags=tags)

    # ── Memory shortcuts ───────────────────────────────────────────────────────

    def remember(self, key: str, value: Any) -> None:
        """Store a value in working (short-term) memory."""
        self._memory.remember(key, value)

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from working (short-term) memory."""
        return self._memory.recall(key, default)

    def persist(self, key: str, value: Any, tags: list[str] | None = None) -> None:
        """Persist a value to long-term (SQLite) memory."""
        self._memory.persist(key, value, tags)

    def retrieve(self, key: str) -> Any | None:
        """Retrieve a value from long-term (SQLite) memory."""
        return self._memory.retrieve(key)

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def ask_llm(
        self,
        prompt: str,
        system: str = "You are a helpful career management AI assistant.",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a prompt to the configured LLM and return the response text.

        Automatically falls back from OpenAI → Ollama based on settings.
        Returns an empty string on failure.
        """
        if settings.use_ollama:
            return await self._ask_ollama(prompt, system, temperature, max_tokens)
        return await self._ask_openai(prompt, system, temperature, max_tokens)

    async def _ask_openai(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            self._log.error("agent.openai_error", error=str(exc))
            return ""

    async def _ask_ollama(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {"temperature": temperature, "num_predict": max_tokens},
                    },
                )
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as exc:
            self._log.error("agent.ollama_error", error=str(exc))
            return ""

    # ── Repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return f"<{self.__class__.__name__} id={self.agent_id!r} status={status}>"
