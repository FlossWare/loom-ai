"""Streaming helpers for loom-ai.

Provides utilities to convert raw ``str``-chunk streams (as produced by
:meth:`~loom_ai.protocols.LLMBackend.chat_stream`) into structured
:class:`~loom_ai.models_phase1.StreamEvent` sequences, accumulate
incremental tool-call deltas, and collapse a stream back into a plain
string.
"""

from __future__ import annotations

from typing import AsyncIterator

from loom_ai.models_phase1 import StreamEvent, ToolCallDelta


class StreamAdapter:
    """Wrap an ``AsyncIterator[str]`` into ``AsyncIterator[StreamEvent]``.

    Each ``str`` chunk becomes a ``StreamEvent(type="content", content=chunk)``.
    A final ``StreamEvent(type="done")`` is emitted after the source is
    exhausted.
    """

    def __init__(self, source: AsyncIterator[str]) -> None:
        self._source = source

    async def __aiter__(self) -> AsyncIterator[StreamEvent]:
        async for chunk in self._source:
            yield StreamEvent(type="content", content=chunk)
        yield StreamEvent(type="done")


class ToolCallAccumulator:
    """Accumulate :class:`ToolCallDelta` fragments into complete calls.

    Deltas sharing the same ``id`` have their ``arguments`` concatenated.
    :meth:`feed` returns ``None`` while the delta is still incomplete,
    and returns the finished :class:`ToolCallDelta` (with
    ``complete=True``) once the final fragment arrives.
    """

    def __init__(self) -> None:
        self._pending: dict[str, ToolCallDelta] = {}

    def feed(self, delta: ToolCallDelta) -> ToolCallDelta | None:
        """Ingest *delta* and return the complete call when ready."""
        if delta.id not in self._pending:
            self._pending[delta.id] = ToolCallDelta(
                id=delta.id,
                name=delta.name,
                arguments=delta.arguments,
                complete=False,
            )
        else:
            self._pending[delta.id].arguments += delta.arguments

        if delta.complete:
            finished = self._pending.pop(delta.id)
            finished.complete = True
            return finished

        return None


async def stream_to_string(stream: AsyncIterator[StreamEvent]) -> str:
    """Collect all ``"content"`` events from *stream* into a single string."""
    parts: list[str] = []
    async for event in stream:
        if event.type == "content" and event.content is not None:
            parts.append(event.content)
    return "".join(parts)


async def stream_to_events(
    stream: AsyncIterator[str],
) -> AsyncIterator[StreamEvent]:
    """Convert a plain ``str``-chunk stream into :class:`StreamEvent` items.

    This is a convenience async generator that behaves identically to
    iterating over a :class:`StreamAdapter`.
    """
    async for chunk in stream:
        yield StreamEvent(type="content", content=chunk)
    yield StreamEvent(type="done")
