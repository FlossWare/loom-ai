"""Tests for loom_ai.backends.streaming."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from loom_ai.backends.streaming import (
    StreamAdapter,
    ToolCallAccumulator,
    stream_to_events,
    stream_to_string,
)
from loom_ai.models_phase1 import StreamEvent, ToolCallDelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _str_stream(*chunks: str) -> AsyncIterator[str]:
    """Return an async iterator that yields the given string chunks."""
    for chunk in chunks:
        yield chunk


async def _failing_stream(*chunks: str) -> AsyncIterator[str]:
    """Yield *chunks* then raise a ``RuntimeError``."""
    for chunk in chunks:
        yield chunk
    raise RuntimeError("stream broke")


# ---------------------------------------------------------------------------
# StreamAdapter
# ---------------------------------------------------------------------------


async def test_stream_adapter_converts_chunks_to_events():
    adapter = StreamAdapter(_str_stream("Hello", " ", "world"))
    events: list[StreamEvent] = []
    async for event in adapter:
        events.append(event)

    content_events = [e for e in events if e.type == "content"]
    assert len(content_events) == 3
    assert content_events[0].content == "Hello"
    assert content_events[1].content == " "
    assert content_events[2].content == "world"


async def test_stream_adapter_emits_done():
    adapter = StreamAdapter(_str_stream("a", "b"))
    events: list[StreamEvent] = []
    async for event in adapter:
        events.append(event)

    assert events[-1].type == "done"
    assert events[-1].content is None


async def test_stream_adapter_empty_source():
    adapter = StreamAdapter(_str_stream())
    events: list[StreamEvent] = []
    async for event in adapter:
        events.append(event)

    assert len(events) == 1
    assert events[0].type == "done"


# ---------------------------------------------------------------------------
# ToolCallAccumulator
# ---------------------------------------------------------------------------


async def test_accumulator_returns_none_until_complete():
    acc = ToolCallAccumulator()

    result = acc.feed(
        ToolCallDelta(id="tc-1", name="search", arguments='{"q": ', complete=False)
    )
    assert result is None

    result = acc.feed(
        ToolCallDelta(id="tc-1", name="search", arguments='"hello"', complete=False)
    )
    assert result is None


async def test_accumulator_concatenates_arguments():
    acc = ToolCallAccumulator()

    acc.feed(
        ToolCallDelta(id="tc-1", name="search", arguments='{"q": ', complete=False)
    )
    acc.feed(
        ToolCallDelta(id="tc-1", name="search", arguments='"hello"', complete=False)
    )
    result = acc.feed(
        ToolCallDelta(id="tc-1", name="search", arguments="}", complete=True)
    )

    assert result is not None
    assert result.id == "tc-1"
    assert result.name == "search"
    assert result.arguments == '{"q": "hello"}'
    assert result.complete is True


async def test_accumulator_handles_multiple_ids():
    acc = ToolCallAccumulator()

    acc.feed(ToolCallDelta(id="tc-1", name="search", arguments="a", complete=False))
    acc.feed(ToolCallDelta(id="tc-2", name="lookup", arguments="x", complete=False))
    acc.feed(ToolCallDelta(id="tc-1", name="search", arguments="b", complete=False))

    r1 = acc.feed(ToolCallDelta(id="tc-1", name="search", arguments="c", complete=True))
    assert r1 is not None
    assert r1.arguments == "abc"

    r2 = acc.feed(ToolCallDelta(id="tc-2", name="lookup", arguments="y", complete=True))
    assert r2 is not None
    assert r2.arguments == "xy"


async def test_accumulator_single_complete_delta():
    acc = ToolCallAccumulator()

    result = acc.feed(
        ToolCallDelta(id="tc-1", name="ping", arguments="{}", complete=True)
    )
    assert result is not None
    assert result.arguments == "{}"
    assert result.complete is True


# ---------------------------------------------------------------------------
# stream_to_string
# ---------------------------------------------------------------------------


async def test_stream_to_string():
    adapter = StreamAdapter(_str_stream("Hello", " ", "world"))
    text = await stream_to_string(adapter)
    assert text == "Hello world"


async def test_stream_to_string_empty():
    adapter = StreamAdapter(_str_stream())
    text = await stream_to_string(adapter)
    assert text == ""


# ---------------------------------------------------------------------------
# stream_to_events
# ---------------------------------------------------------------------------


async def test_stream_to_events():
    events: list[StreamEvent] = []
    async for event in stream_to_events(_str_stream("x", "y")):
        events.append(event)

    assert len(events) == 3
    assert events[0] == StreamEvent(type="content", content="x")
    assert events[1] == StreamEvent(type="content", content="y")
    assert events[2] == StreamEvent(type="done")


async def test_stream_to_events_empty():
    events: list[StreamEvent] = []
    async for event in stream_to_events(_str_stream()):
        events.append(event)

    assert len(events) == 1
    assert events[0].type == "done"


# ---------------------------------------------------------------------------
# Error propagation (#31, #36)
# ---------------------------------------------------------------------------


async def test_stream_adapter_propagates_error():
    """StreamAdapter must re-raise source exceptions and emit an error event."""
    adapter = StreamAdapter(_failing_stream("a", "b"))
    events: list[StreamEvent] = []

    with pytest.raises(RuntimeError, match="stream broke"):
        async for event in adapter:
            events.append(event)

    # Two content events + one error event (no "done")
    assert len(events) == 3
    assert events[0] == StreamEvent(type="content", content="a")
    assert events[1] == StreamEvent(type="content", content="b")
    assert events[2].type == "error"
    assert "stream broke" in (events[2].content or "")


async def test_stream_adapter_error_on_first_chunk():
    """StreamAdapter emits an error event even when the first chunk fails."""

    async def _immediate_fail() -> AsyncIterator[str]:
        raise RuntimeError("instant failure")
        yield ""  # pragma: no cover -- makes this an async generator

    adapter = StreamAdapter(_immediate_fail())
    events: list[StreamEvent] = []

    with pytest.raises(RuntimeError, match="instant failure"):
        async for event in adapter:
            events.append(event)

    assert len(events) == 1
    assert events[0].type == "error"


async def test_stream_to_events_propagates_error():
    """stream_to_events must re-raise source exceptions and emit error."""
    events: list[StreamEvent] = []

    event_stream = stream_to_events(_failing_stream("x"))
    with pytest.raises(RuntimeError, match="stream broke"):
        async for event in event_stream:
            events.append(event)

    assert len(events) == 2
    assert events[0] == StreamEvent(type="content", content="x")
    assert events[1].type == "error"
    assert "stream broke" in (events[1].content or "")


async def test_stream_to_string_propagates_error():
    """stream_to_string must propagate errors from the underlying stream."""
    adapter = StreamAdapter(_failing_stream("partial"))

    with pytest.raises(RuntimeError, match="stream broke"):
        await stream_to_string(adapter)
