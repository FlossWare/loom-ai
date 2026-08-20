"""Session persistence and knowledge extraction for loom-ai.

Covers the demo persistence chain:
- #683: Persist session state across process termination
- #684: Extract, chunk, embed, and persist engineering knowledge
- #685: Retrieve prior knowledge in a fresh session
- #686: Use recovered knowledge for follow-up tasks

Usage::

    from loom_ai.session_persistence import SessionManager
    mgr = SessionManager(memory=backend, knowledge=pipeline)

    # Session 1: work and persist
    sid = await mgr.create_session(project="loom-ai")
    await mgr.record_event(sid, "found bug in parser")
    await mgr.persist(sid)

    # Session 2: recover and continue
    ctx = await mgr.recover_context(project="loom-ai", query="parser")
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loom_ai.contracts_phase1 import (
        KnowledgePipeline,
        PersistentMemoryBackend,
    )


@dataclass
class SessionEvent:
    """A discrete event within a session."""

    kind: str
    content: str
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionState:
    """Durable session state."""

    session_id: str
    project: str
    events: list[SessionEvent] = field(default_factory=list)
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RecoveredContext:
    """Context assembled from prior sessions."""

    memories: list[dict] = field(default_factory=list)
    knowledge: list[dict] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)


class SessionManager:
    """Manages session persistence and knowledge recovery.

    Bridges session state (in-memory during execution) with durable
    storage (PersistentMemoryBackend + KnowledgePipeline).
    """

    def __init__(
        self,
        *,
        memory: PersistentMemoryBackend | None = None,
        knowledge: KnowledgePipeline | None = None,
    ) -> None:
        self._memory = memory
        self._knowledge = knowledge
        self._sessions: dict[str, SessionState] = {}

    async def create_session(
        self,
        project: str = "",
        *,
        metadata: dict | None = None,
    ) -> str:
        """Create a new tracked session."""
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        state = SessionState(
            session_id=sid,
            project=project,
            created_at=now,
            metadata=metadata or {},
        )
        self._sessions[sid] = state
        return sid

    async def record_event(
        self,
        session_id: str,
        content: str,
        *,
        kind: str = "observation",
        metadata: dict | None = None,
    ) -> None:
        """Record a discrete event within the session."""
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"Session not found: {session_id}")
        now = datetime.now(timezone.utc).isoformat()
        state.events.append(
            SessionEvent(
                kind=kind,
                content=content,
                timestamp=now,
                metadata=metadata or {},
            )
        )

    async def persist(self, session_id: str) -> dict[str, Any]:
        """Persist session state to memory and knowledge backends.

        Returns a summary of what was persisted.
        """
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"Session not found: {session_id}")

        result: dict[str, Any] = {
            "session_id": session_id,
            "memory_stored": False,
            "knowledge_stored": False,
        }

        if self._memory is not None:
            session_content = json.dumps(
                {
                    "session_id": state.session_id,
                    "project": state.project,
                    "created_at": state.created_at,
                    "events": [
                        {
                            "kind": e.kind,
                            "content": e.content,
                            "timestamp": e.timestamp,
                        }
                        for e in state.events
                    ],
                }
            )
            await self._memory.store(
                f"session/{session_id}",
                session_content,
                memory_type="session",
                metadata={
                    "project": state.project,
                    "event_count": len(state.events),
                    "scope": "project",
                },
            )
            result["memory_stored"] = True

        if self._knowledge is not None:
            knowledge_text = self._extract_knowledge(state)
            if knowledge_text:
                doc_id = await self._knowledge.ingest(
                    knowledge_text,
                    metadata={
                        "type": "session_knowledge",
                        "session_id": session_id,
                        "project": state.project,
                        "source": f"session/{session_id}",
                    },
                )
                result["knowledge_stored"] = True
                result["knowledge_doc_id"] = doc_id

        return result

    @staticmethod
    def _extract_knowledge(state: SessionState) -> str:
        """Extract engineering knowledge from session events."""
        parts = []
        for event in state.events:
            if event.kind in (
                "observation",
                "decision",
                "discovery",
                "fix",
            ):
                parts.append(f"[{event.kind}] {event.content}")
        if not parts:
            return ""
        header = f"Project: {state.project}\n"
        header += f"Session: {state.session_id}\n\n"
        return header + "\n".join(parts)

    async def _recover_memories(
        self,
        ctx: RecoveredContext,
        query: str,
        project: str,
        limit: int,
    ) -> None:
        """Search memory backend and append matching records."""
        if self._memory is None:
            return
        records = await self._memory.search(
            query,
            limit=limit,
            memory_type="session",
        )
        for r in records:
            if project and r.metadata.get("project") != project:
                continue
            ctx.memories.append(
                {
                    "name": r.name,
                    "content": r.content,
                    "type": r.memory_type,
                    "metadata": r.metadata,
                }
            )
            ctx.provenance.append(f"memory:{r.name}")

    async def _recover_knowledge(
        self,
        ctx: RecoveredContext,
        query: str,
        project: str,
        limit: int,
    ) -> None:
        """Search knowledge backend and append matching results."""
        if self._knowledge is None:
            return
        results = await self._knowledge.query(
            query,
            limit=limit,
        )
        for r in results:
            if project and r.metadata.get("project") != project:
                continue
            ctx.knowledge.append(
                {
                    "content": r.content,
                    "score": r.score,
                    "source": r.source,
                    "metadata": r.metadata,
                }
            )
            ctx.provenance.append(f"knowledge:{r.source}")

    async def recover_context(
        self,
        *,
        project: str = "",
        query: str = "",
        limit: int = 10,
    ) -> RecoveredContext:
        """Recover context from prior sessions.

        Searches both memory (session records) and knowledge
        (extracted engineering knowledge) backends.  When *project*
        is given, results are filtered to that project.
        """
        ctx = RecoveredContext()
        if query:
            await self._recover_memories(ctx, query, project, limit)
            await self._recover_knowledge(ctx, query, project, limit)
        return ctx

    async def get_session(
        self,
        session_id: str,
    ) -> SessionState | None:
        """Return the in-memory session state, or None."""
        return self._sessions.get(session_id)
