"""In-memory conversation session manager for loom-ai.

Implements :class:`~loom_ai.contracts_phase1.ConversationManager` using
plain dicts -- no external dependencies.  Suitable for testing, local
development, and the *crush* deployment profile.  All data is lost on
process exit.

Token estimation uses a 4-characters-per-token heuristic throughout.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict

from loom_ai.models import ChatMessage


def _estimate_tokens(message: ChatMessage) -> int:
    """Estimate token count for a single message (4 chars per token)."""
    return max(1, len(message.content) // 4)


class InMemoryConversationManager:
    """Dict-backed conversation session manager.

    Satisfies :class:`~loom_ai.contracts_phase1.ConversationManager` via
    structural subtyping.

    Each session stores an ordered message list and optional metadata.
    Token-budget operations use a 4-characters-per-token heuristic.
    """

    def __init__(self) -> None:
        # session_id -> {"messages": list[ChatMessage], "metadata": dict}
        self._sessions: dict[str, dict] = {}

    def _require_session(self, session_id: str) -> dict:
        """Return the session dict or raise ``KeyError``."""
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"Session '{session_id}' does not exist") from None

    async def create_session(self, *, metadata: dict | None = None) -> str:
        """Create a new conversation session and return its id."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "messages": [],
            "metadata": metadata or {},
        }
        return session_id

    async def add_message(self, session_id: str, message: ChatMessage) -> None:
        """Append a message to the session history."""
        session = self._require_session(session_id)
        session["messages"].append(message)

    async def get_messages(
        self, session_id: str, *, max_tokens: int | None = None
    ) -> list[ChatMessage]:
        """Return messages for the session, optionally trimmed to a token budget.

        When *max_tokens* is specified, the oldest messages are dropped
        until the total estimated token count fits within the budget.
        The most recent message is always included.
        """
        session = self._require_session(session_id)
        messages: list[ChatMessage] = list(session["messages"])

        if max_tokens is None or not messages:
            return messages

        # Walk backwards from the end, accumulating tokens
        total = 0
        start_index = len(messages)
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = _estimate_tokens(messages[i])
            if total + msg_tokens > max_tokens:
                break
            total += msg_tokens
            start_index = i

        return messages[start_index:]

    async def compress(self, session_id: str, *, target_tokens: int) -> None:
        """Compress the session history to fit within *target_tokens*.

        Drops the oldest messages until the remaining history fits.
        """
        session = self._require_session(session_id)
        messages: list[ChatMessage] = session["messages"]

        while messages:
            total = sum(_estimate_tokens(m) for m in messages)
            if total <= target_tokens:
                break
            messages.pop(0)

    async def fork(self, session_id: str) -> str:
        """Create a deep copy of the session and return the new session id."""
        session = self._require_session(session_id)
        new_id = str(uuid.uuid4())
        self._sessions[new_id] = copy.deepcopy(session)
        return new_id

    async def export_transcript(self, session_id: str) -> list[dict]:
        """Export the full session transcript as a list of plain dicts."""
        session = self._require_session(session_id)
        return [asdict(msg) for msg in session["messages"]]

    async def archive(self, session_id: str) -> str:
        """Archive a session and return the session id.

        In-memory implementation stores a frozen copy of the transcript
        under an ``archived_`` prefix.  Persistent implementations
        should write to a ``TranscriptStore``.
        """
        session = self._require_session(session_id)
        archive_id = f"archived_{session_id}"
        self._sessions[archive_id] = copy.deepcopy(session)
        return archive_id
