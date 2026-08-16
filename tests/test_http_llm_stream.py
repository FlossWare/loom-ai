"""Tests for HttpLLMBackend.chat_stream error propagation (#31, #36).

These tests verify that ``chat_stream`` surfaces exceptions to callers
instead of silently swallowing them.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from loom_ai.backends.http_llm import HttpLLMBackend
from loom_ai.models import ChatMessage


def _make_backend(**kwargs) -> HttpLLMBackend:
    return HttpLLMBackend(
        base_url="http://localhost:9999",
        api_key="test-key",
        default_model="test-model",
        **kwargs,
    )


def _sse_lines(*data_payloads: str, done: bool = True) -> bytes:
    """Build raw SSE byte content from data payloads."""
    lines: list[str] = []
    for payload in data_payloads:
        lines.append(f"data: {payload}")
    if done:
        lines.append("data: [DONE]")
    return "\n".join(lines).encode("utf-8")


def _chunk_json(content: str) -> str:
    """Return a minimal SSE chunk JSON string."""
    return json.dumps({"choices": [{"delta": {"content": content}}]})


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


async def test_chat_stream_propagates_http_error():
    """HTTPError during streaming must raise RuntimeError to the caller."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hello")]

    exc = urllib.error.HTTPError(
        url="http://localhost:9999/chat/completions",
        code=500,
        msg="Internal Server Error",
        hdrs=MagicMock(),
        fp=io.BytesIO(b"server error body"),
    )

    with patch("urllib.request.urlopen", side_effect=exc):
        with pytest.raises(RuntimeError, match="LLM streaming error 500"):
            chunks = []
            async for chunk in backend.chat_stream(msgs):
                chunks.append(chunk)


async def test_chat_stream_propagates_url_error():
    """URLError during streaming must raise RuntimeError to the caller."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hello")]

    exc = urllib.error.URLError(reason="Connection refused")

    with patch("urllib.request.urlopen", side_effect=exc):
        with pytest.raises(RuntimeError, match="LLM streaming connection error"):
            async for _ in backend.chat_stream(msgs):
                pass


async def test_chat_stream_propagates_generic_exception():
    """Unexpected exceptions during streaming must raise RuntimeError."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hello")]

    with patch("urllib.request.urlopen", side_effect=OSError("disk full")):
        with pytest.raises(RuntimeError, match="LLM streaming error"):
            async for _ in backend.chat_stream(msgs):
                pass


async def test_chat_stream_yields_content_before_error():
    """Partial content must be yielded before an error is raised."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hello")]

    # Build a fake response that yields one good chunk then errors
    good_line = f"data: {_chunk_json('partial')}\n".encode()

    class _FailingResponse:
        """Simulates a response that yields lines then raises."""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def __iter__(self):
            yield good_line
            raise ConnectionError("connection reset")

    with patch("urllib.request.urlopen", return_value=_FailingResponse()):
        collected: list[str] = []
        with pytest.raises(RuntimeError, match="LLM streaming error"):
            async for chunk in backend.chat_stream(msgs):
                collected.append(chunk)

        assert collected == ["partial"]


async def test_chat_stream_happy_path():
    """Verify normal streaming still works after the error-handling changes."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hello")]

    body = _sse_lines(_chunk_json("Hello"), _chunk_json(" world"))
    fake_resp = MagicMock()
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.__iter__ = MagicMock(return_value=iter(body.split(b"\n") + [b""]))

    # Each line needs to decode properly -- patch urlopen to return our mock
    # but we need lines as bytes with newlines
    lines = [line + b"\n" for line in body.split(b"\n")]
    fake_resp.__iter__ = MagicMock(return_value=iter(lines))

    with patch("urllib.request.urlopen", return_value=fake_resp):
        collected: list[str] = []
        async for chunk in backend.chat_stream(msgs):
            collected.append(chunk)

        assert collected == ["Hello", " world"]
