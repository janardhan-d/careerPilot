"""
CareerPilot — Tool Registry
============================
Shared, decorator-based tool registry. Agents discover and invoke tools
through this central registry — promoting loose coupling and reusability.

Usage
-----
Register a tool:
>>> @registry.tool(name="search_jobs", description="Search job boards")
... async def search_jobs(query: JobSearchInput) -> list[JobPosting]:
...     ...

Invoke a tool from any agent:
>>> result = await registry.invoke("search_jobs", payload={"query": "ML Engineer"})

List available tools:
>>> registry.list_tools()
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ToolDefinition:
    """Metadata and callable for a registered tool."""

    name: str
    description: str
    fn: Callable[..., Coroutine[Any, Any, Any]]
    input_schema: type[BaseModel] | None
    tags: list[str] = field(default_factory=list)
    call_count: int = field(default=0, repr=False)
    total_latency_ms: float = field(default=0.0, repr=False)

    @property
    def avg_latency_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count


class ToolRegistry:
    """
    Central registry for all CareerPilot tools.

    Features
    --------
    - Decorator-based registration via @registry.tool(...)
    - Input validation via Pydantic when input_schema is provided
    - Per-tool call metrics (count, avg latency)
    - Tag-based tool filtering
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def tool(
        self,
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        input_schema: type[BaseModel] | None = None,
    ) -> Callable[[F], F]:
        """
        Decorator that registers an async function as a tool.

        Parameters
        ----------
        name:         Tool name (defaults to function name).
        description:  Human-readable description shown to agents / LLM.
        tags:         Optional labels for filtering (e.g. ["linkedin", "read"]).
        input_schema: Pydantic model for input validation.
        """

        def decorator(fn: F) -> F:
            if not asyncio.iscoroutinefunction(fn):
                raise TypeError(f"Tool '{fn.__name__}' must be an async function.")

            tool_name = name or fn.__name__
            self._tools[tool_name] = ToolDefinition(
                name=tool_name,
                description=description or (inspect.getdoc(fn) or ""),
                fn=fn,
                input_schema=input_schema,
                tags=tags or [],
            )
            logger.debug("tool_registry.registered", tool=tool_name, tags=tags or [])
            return fn

        return decorator  # type: ignore[return-value]

    def register(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        input_schema: type[BaseModel] | None = None,
    ) -> None:
        """Register a tool imperatively (no decorator)."""
        self.tool(name=name, description=description, tags=tags, input_schema=input_schema)(fn)

    # ── Invocation ────────────────────────────────────────────────────────────

    async def invoke(
        self,
        tool_name: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Invoke a registered tool by name.

        Parameters
        ----------
        tool_name: Name of the registered tool.
        payload:   Dict of arguments (merged with kwargs).
        **kwargs:  Additional keyword arguments.

        Raises
        ------
        KeyError:  If the tool name is not registered.
        Exception: Re-raises any exception from the tool after logging.
        """
        if tool_name not in self._tools:
            available = ", ".join(sorted(self._tools))
            raise KeyError(
                f"Tool '{tool_name}' not found. Available tools: {available}"
            )

        tool = self._tools[tool_name]
        args = {**(payload or {}), **kwargs}

        # Validate input if schema is declared
        if tool.input_schema is not None:
            validated = tool.input_schema(**args)
            args = validated.model_dump()

        t0 = time.perf_counter()
        try:
            result = await tool.fn(**args)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            tool.call_count += 1
            tool.total_latency_ms += elapsed_ms
            logger.info(
                "tool.invoked",
                tool=tool_name,
                latency_ms=round(elapsed_ms, 2),
                call_count=tool.call_count,
            )
            return result
        except Exception as exc:
            logger.exception("tool.error", tool=tool_name, error=str(exc))
            raise

    # ── Discovery ─────────────────────────────────────────────────────────────

    def list_tools(self, tags: list[str] | None = None) -> list[dict[str, Any]]:
        """
        List all registered tools, optionally filtered by tags.

        Returns a list of dicts suitable for passing to an LLM function-calling API.
        """
        tools = list(self._tools.values())
        if tags:
            tools = [t for t in tools if any(tag in t.tags for tag in tags)]
        return [
            {
                "name": t.name,
                "description": t.description,
                "tags": t.tags,
                "avg_latency_ms": round(t.avg_latency_ms, 1),
                "call_count": t.call_count,
            }
            for t in tools
        ]

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Return the ToolDefinition for *name*, or None if not found."""
        return self._tools.get(name)

    def stats(self) -> dict[str, Any]:
        """Return aggregate registry statistics."""
        return {
            "total_tools": len(self._tools),
            "tools": {
                name: {
                    "call_count": t.call_count,
                    "avg_latency_ms": round(t.avg_latency_ms, 1),
                }
                for name, t in self._tools.items()
            },
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ── Global singleton ──────────────────────────────────────────────────────────
registry = ToolRegistry()
