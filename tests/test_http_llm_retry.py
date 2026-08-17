"""Tests for HttpLLMBackend retry with exponential backoff (#274).

Verifies that ``chat()`` and ``chat_stream()`` retry on transient errors
(HTTP 429/5xx, connection failures) and raise immediately on
non-retryable client errors (4xx except 429).
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, call, patch

import pytest

from loom_ai.backends.http_llm import _RETRY_MAX, HttpLLMBackend
from loom_ai.models import ChatMessage

# ── helpers ─────────────────────────────────────────────────────────


def _make_backend(**kwargs) -> HttpLLMBackend:
    return HttpLLMBackend(
        base_url="http://localhost:9999",
        api_key="test-key",
        default_model="test-model",
        **kwargs,
    )


def _success_response(content: str = "Hello") -> MagicMock:
    """Build a mock urllib response for a successful chat completion."""
    data = {
        "choices": [{"message": {"content": content}}],
        "model": "test-model",
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 3,
            "total_tokens": 8,
        },
    }
    body = json.dumps(data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int, msg: str = "error") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://localhost:9999/chat/completions",
        code=code,
        msg=msg,
        hdrs=MagicMock(),
        fp=io.BytesIO(msg.encode()),
    )


def _chunk_json(content: str) -> str:
    """Return a minimal SSE chunk JSON string."""
    return json.dumps({"choices": [{"delta": {"content": content}}]})


def _stream_response(*data_payloads: str) -> MagicMock:
    """Build a mock response for streaming SSE."""
    lines: list[bytes] = []
    for payload in data_payloads:
        lines.append(f"data: {payload}\n".encode("utf-8"))
    lines.append(b"data: [DONE]\n")

    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.__iter__ = MagicMock(return_value=iter(lines))
    return resp


# ── chat() tests ────────────────────────────────────────────────────


@patch("time.sleep")
async def test_chat_success_no_retry(mock_sleep):
    """Successful call should not trigger any retries."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hi")]

    with patch("urllib.request.urlopen", return_value=_success_response()):
        result = await backend.chat(msgs)

    assert result.content == "Hello"
    mock_sleep.assert_not_called()


@patch("time.sleep")
async def test_chat_retry_on_429(mock_sleep):
    """429 should be retried; success on 2nd attempt."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.5)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[_http_error(429, "rate limited"), _success_response()],
    ):
        result = await backend.chat(msgs)

    assert result.content == "Hello"
    assert mock_sleep.call_count == 1
    # 2^0 + 0.5 jitter = 1.5
    mock_sleep.assert_called_once_with(1.5)


@patch("time.sleep")
async def test_chat_retry_on_503_with_backoff(mock_sleep):
    """503 should be retried with exponential backoff."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.0)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[
            _http_error(503, "unavailable"),
            _http_error(503, "unavailable"),
            _http_error(503, "unavailable"),
            _success_response(),
        ],
    ):
        result = await backend.chat(msgs)

    assert result.content == "Hello"
    assert mock_sleep.call_count == 3
    # 2^0=1, 2^1=2, 2^2=4 (jitter=0)
    mock_sleep.assert_has_calls([call(1.0), call(2.0), call(4.0)])


@patch("time.sleep")
async def test_chat_no_retry_on_400(mock_sleep):
    """400 (client error) should raise immediately -- no retries."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(400, "bad request"),
    ):
        with pytest.raises(RuntimeError, match="LLM API error 400"):
            await backend.chat(msgs)

    mock_sleep.assert_not_called()


@patch("time.sleep")
async def test_chat_no_retry_on_422(mock_sleep):
    """422 (validation error) should raise immediately -- no retries."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(422, "unprocessable"),
    ):
        with pytest.raises(RuntimeError, match="LLM API error 422"):
            await backend.chat(msgs)

    mock_sleep.assert_not_called()


@patch("time.sleep")
async def test_chat_exhausts_retries(mock_sleep):
    """All retries exhausted should raise the last error."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.0)
    msgs = [ChatMessage(role="user", content="hi")]

    errors = [_http_error(500, "server error") for _ in range(_RETRY_MAX + 1)]
    with patch("urllib.request.urlopen", side_effect=errors):
        with pytest.raises(RuntimeError, match="LLM API error 500"):
            await backend.chat(msgs)

    assert mock_sleep.call_count == _RETRY_MAX


@patch("time.sleep")
async def test_chat_retry_on_connection_error(mock_sleep):
    """URLError (connection failure) should be retried."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.0)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[
            urllib.error.URLError("Connection refused"),
            _success_response(),
        ],
    ):
        result = await backend.chat(msgs)

    assert result.content == "Hello"
    assert mock_sleep.call_count == 1


@patch("time.sleep")
async def test_chat_backoff_capped_at_max(mock_sleep):
    """Backoff delay must never exceed _RETRY_BACKOFF_CAP."""
    backend = _make_backend()
    # Large jitter to push total above cap
    backend._rng.uniform = MagicMock(return_value=100.0)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[
            _http_error(500, "error"),
            _success_response(),
        ],
    ):
        result = await backend.chat(msgs)

    assert result.content == "Hello"
    # min(2^0 + 100, 10) = 10
    mock_sleep.assert_called_once_with(10.0)


# ── chat_stream() tests ────────────────────────────────────────────


@patch("time.sleep")
async def test_stream_retry_on_429(mock_sleep):
    """429 during streaming connection should be retried."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.5)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[
            _http_error(429, "rate limited"),
            _stream_response(_chunk_json("hi")),
        ],
    ):
        chunks: list[str] = []
        async for chunk in backend.chat_stream(msgs):
            chunks.append(chunk)

    assert chunks == ["hi"]
    assert mock_sleep.call_count == 1


@patch("time.sleep")
async def test_stream_no_retry_on_400(mock_sleep):
    """400 during streaming connection should raise immediately."""
    backend = _make_backend()
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(400, "bad request"),
    ):
        with pytest.raises(RuntimeError, match="LLM streaming error 400"):
            async for _ in backend.chat_stream(msgs):
                pass

    mock_sleep.assert_not_called()


@patch("time.sleep")
async def test_stream_exhausts_retries_on_503(mock_sleep):
    """All retries exhausted during streaming raises error."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.0)
    msgs = [ChatMessage(role="user", content="hi")]

    errors = [_http_error(503, "unavailable") for _ in range(_RETRY_MAX + 1)]
    with patch("urllib.request.urlopen", side_effect=errors):
        with pytest.raises(RuntimeError, match="LLM streaming error 503"):
            async for _ in backend.chat_stream(msgs):
                pass

    assert mock_sleep.call_count == _RETRY_MAX


@patch("time.sleep")
async def test_stream_retry_on_url_error(mock_sleep):
    """URLError during streaming connection should be retried."""
    backend = _make_backend()
    backend._rng.uniform = MagicMock(return_value=0.0)
    msgs = [ChatMessage(role="user", content="hi")]

    with patch(
        "urllib.request.urlopen",
        side_effect=[
            urllib.error.URLError("Connection refused"),
            _stream_response(_chunk_json("recovered")),
        ],
    ):
        chunks: list[str] = []
        async for chunk in backend.chat_stream(msgs):
            chunks.append(chunk)

    assert chunks == ["recovered"]
    assert mock_sleep.call_count == 1
