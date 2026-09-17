"""
CareerPilot — Agent Memory
===========================
Two-tier memory system for agents:

1. **Working Memory** (short-term) — TTL-based in-process cache.
   Fast, ephemeral. Cleared between sessions.

2. **Long-Term Memory** (persistent) — SQLite-backed key/value + full-text
   search. Survives restarts. Shared across agents.

Usage
-----
>>> mem = Memory(agent_id="tracker")
>>> await mem.remember("last_search", {"query": "ML Engineer", "ts": ...})
>>> entry = await mem.recall("last_search")
>>> results = await mem.search("ML Engineer")
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from cachetools import TTLCache

logger = structlog.get_logger(__name__)

# Default TTL for working memory entries (30 minutes)
DEFAULT_TTL_SECONDS = 1800
# Maximum entries in working memory per agent
WORKING_MEMORY_MAXSIZE = 512


class WorkingMemory:
    """
    In-process TTL cache for short-lived agent state.

    Thread-safe (cachetools TTLCache uses a RLock internally).
    """

    def __init__(self, agent_id: str, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self.agent_id = agent_id
        self._cache: TTLCache[str, Any] = TTLCache(
            maxsize=WORKING_MEMORY_MAXSIZE, ttl=ttl
        )

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* (resets TTL)."""
        self._cache[f"{self.agent_id}:{key}"] = value
        logger.debug("working_memory.set", agent=self.agent_id, key=key)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve *key*; return *default* if missing or expired."""
        return self._cache.get(f"{self.agent_id}:{key}", default)

    def delete(self, key: str) -> None:
        """Remove *key* from the cache."""
        self._cache.pop(f"{self.agent_id}:{key}", None)

    def clear(self) -> None:
        """Flush all entries for this agent."""
        keys = [k for k in self._cache if k.startswith(f"{self.agent_id}:")]
        for k in keys:
            self._cache.pop(k, None)

    def keys(self) -> list[str]:
        """List active (non-expired) keys for this agent."""
        prefix = f"{self.agent_id}:"
        return [k[len(prefix):] for k in self._cache if k.startswith(prefix)]

    def __len__(self) -> int:
        return sum(1 for k in self._cache if k.startswith(f"{self.agent_id}:"))


class LongTermMemory:
    """
    Persistent key/value store backed by SQLite.

    Uses a simple `memories` table with:
        agent_id | key | value (JSON) | tags (JSON list) | updated_at (epoch)

    All methods are sync (SQLite doesn't need async for small workloads).
    Wrap with asyncio.to_thread() in hot paths if needed.
    """

    def __init__(self, db_path: str = "./careerpilot.db") -> None:
        self._db_path = db_path
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> Any:
        import sqlite3  # lazy import — avoid top-level dep in tests
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                agent_id   TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                tags       TEXT DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (agent_id, key)
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories (tags)"
        )
        self._conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def store(
        self,
        agent_id: str,
        key: str,
        value: Any,
        tags: list[str] | None = None,
    ) -> None:
        """Upsert a memory entry."""
        self._conn.execute(
            """
            INSERT INTO memories (agent_id, key, value, tags, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, key) DO UPDATE SET
                value = excluded.value,
                tags = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (agent_id, key, json.dumps(value), json.dumps(tags or []), time.time()),
        )
        self._conn.commit()
        logger.debug("long_term_memory.stored", agent=agent_id, key=key)

    def retrieve(self, agent_id: str, key: str) -> Any | None:
        """Fetch a memory entry by agent_id + key. Returns None if missing."""
        row = self._conn.execute(
            "SELECT value FROM memories WHERE agent_id = ? AND key = ?",
            (agent_id, key),
        ).fetchone()
        return json.loads(row["value"]) if row else None

    def delete(self, agent_id: str, key: str) -> None:
        """Remove a single memory entry."""
        self._conn.execute(
            "DELETE FROM memories WHERE agent_id = ? AND key = ?", (agent_id, key)
        )
        self._conn.commit()

    def search_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Return all memories that include *tag* in their tags list."""
        rows = self._conn.execute(
            "SELECT agent_id, key, value, tags, updated_at FROM memories"
        ).fetchall()
        results = []
        for row in rows:
            if tag in json.loads(row["tags"]):
                results.append(
                    {
                        "agent_id": row["agent_id"],
                        "key": row["key"],
                        "value": json.loads(row["value"]),
                        "tags": json.loads(row["tags"]),
                        "updated_at": row["updated_at"],
                    }
                )
        return results

    def list_keys(self, agent_id: str) -> list[str]:
        """List all keys stored for *agent_id*."""
        rows = self._conn.execute(
            "SELECT key FROM memories WHERE agent_id = ?", (agent_id,)
        ).fetchall()
        return [r["key"] for r in rows]


class Memory:
    """
    Unified memory interface for an agent.

    Combines WorkingMemory (fast, ephemeral) and LongTermMemory (persistent).

    Usage
    -----
    >>> mem = Memory("tracker")
    >>> mem.remember("scan_state", {...})        # working memory
    >>> mem.persist("last_run", {...})           # long-term memory
    >>> mem.recall("scan_state")                 # working memory lookup
    >>> mem.retrieve("last_run")                 # long-term memory lookup
    """

    def __init__(self, agent_id: str, db_path: str = "./careerpilot.db") -> None:
        self.agent_id = agent_id
        self.working = WorkingMemory(agent_id=agent_id)
        self.long_term = LongTermMemory(db_path=db_path)

    # ── Working memory shortcuts ───────────────────────────────────────────────
    def remember(self, key: str, value: Any) -> None:
        """Store in working (short-term) memory."""
        self.working.set(key, value)

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve from working (short-term) memory."""
        return self.working.get(key, default)

    # ── Long-term memory shortcuts ─────────────────────────────────────────────
    def persist(self, key: str, value: Any, tags: list[str] | None = None) -> None:
        """Persist to long-term (SQLite) memory."""
        self.long_term.store(self.agent_id, key, value, tags)

    def retrieve(self, key: str) -> Any | None:
        """Retrieve from long-term (SQLite) memory."""
        return self.long_term.retrieve(self.agent_id, key)
