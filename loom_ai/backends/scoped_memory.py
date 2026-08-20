"""Scoped memory adapter over PersistentMemoryBackend.

Provides agent-scoped, session-scoped, or project-scoped views of the
canonical :class:`~loom_ai.contracts_core.PersistentMemoryBackend`.
Replaces the need for a separate ``AgentMemory`` store.

This is the canonical way to get scoped memory access in loom-ai.
The underlying store holds all memories; the adapter filters by scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loom_ai.contracts_core import PersistentMemoryBackend
    from loom_ai.models_core import MemoryRecord


class ScopedMemoryView:
    """Scoped view over a ``PersistentMemoryBackend``.

    All reads are filtered to the configured scope; all writes
    automatically tag entries with scope, agent_id, and session_id.
    """

    def __init__(
        self,
        backend: PersistentMemoryBackend,
        *,
        scope: str = "global",
        agent_id: str = "",
        session_id: str = "",
    ) -> None:
        self._backend = backend
        self._scope = scope
        self._agent_id = agent_id
        self._session_id = session_id

    def _enrich_metadata(self, metadata: dict | None) -> dict:
        m = dict(metadata or {})
        m["scope"] = self._scope
        if self._agent_id:
            m["agent_id"] = self._agent_id
        if self._session_id:
            m["session_id"] = self._session_id
        return m

    async def store(
        self,
        name: str,
        content: str,
        *,
        memory_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Store a memory tagged with this view's scope."""
        scoped_name = f"{self._scope}/{name}"
        return await self._backend.store(
            scoped_name,
            content,
            memory_type=memory_type,
            metadata=self._enrich_metadata(metadata),
        )

    async def recall(self, name: str) -> MemoryRecord | None:
        """Recall a memory by name within this scope."""
        return await self._backend.recall(f"{self._scope}/{name}")

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """Search memories, returning only those in this scope."""
        results = await self._backend.search(
            query,
            limit=limit * 3,
            memory_type=memory_type,
        )
        filtered = [r for r in results if r.metadata.get("scope") == self._scope]
        return filtered[:limit]

    async def forget(self, name: str) -> bool:
        """Remove a scoped memory."""
        return await self._backend.forget(f"{self._scope}/{name}")

    async def list_memories(
        self,
        *,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """List memories in this scope."""
        all_memories = await self._backend.list_memories(
            memory_type=memory_type,
        )
        return [m for m in all_memories if m.metadata.get("scope") == self._scope]
