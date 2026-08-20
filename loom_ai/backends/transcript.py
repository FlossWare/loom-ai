"""In-memory transcript storage backend for loom-ai.

Provides ``InMemoryTranscriptStore``, a dict-backed implementation of
:class:`~loom_ai.contracts_workflow.TranscriptStore`.  All data is lost
on process exit.  Suitable for testing and local development.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from loom_ai.models import ChatMessage
from loom_ai.models_workflow import TranscriptSummary


@dataclass
class _SessionRecord:
    """Internal record for a stored transcript session."""

    session_id: str
    messages: list[ChatMessage]
    created_at: str
    metadata: dict = field(default_factory=dict)


class InMemoryTranscriptStore:
    """Dict-backed transcript store.

    Satisfies :class:`~loom_ai.contracts_workflow.TranscriptStore` via
    structural subtyping -- no inheritance required.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionRecord] = {}

    async def store(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        metadata: dict | None = None,
    ) -> None:
        """Store messages for a session, overwriting any previous data."""
        self._sessions[session_id] = _SessionRecord(
            session_id=session_id,
            messages=list(messages),
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

    async def load(self, session_id: str) -> list[ChatMessage]:
        """Return messages for *session_id*, or an empty list if not found."""
        record = self._sessions.get(session_id)
        if record is None:
            return []
        return list(record.messages)

    async def search(self, query: str, *, limit: int = 10) -> list[TranscriptSummary]:
        """Substring match across message content, returning summaries.

        The ``preview`` field contains the first 100 characters of the
        first matching message's content.
        """
        query_lower = query.lower()
        matches: list[TranscriptSummary] = []

        for record in self._sessions.values():
            for msg in record.messages:
                if query_lower in msg.content.lower():
                    preview = msg.content[:100]
                    matches.append(
                        TranscriptSummary(
                            session_id=record.session_id,
                            created_at=record.created_at,
                            message_count=len(record.messages),
                            preview=preview,
                            metadata=dict(record.metadata),
                        )
                    )
                    break  # one match per session is enough

            if len(matches) >= limit:
                break

        return matches[:limit]

    async def list_sessions(self, *, limit: int = 20) -> list[TranscriptSummary]:
        """Return most recent sessions sorted by created_at descending."""
        records = sorted(
            self._sessions.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )

        summaries: list[TranscriptSummary] = []
        for record in records[:limit]:
            preview = ""
            if record.messages:
                preview = record.messages[0].content[:100]
            summaries.append(
                TranscriptSummary(
                    session_id=record.session_id,
                    created_at=record.created_at,
                    message_count=len(record.messages),
                    preview=preview,
                    metadata=dict(record.metadata),
                )
            )

        return summaries
