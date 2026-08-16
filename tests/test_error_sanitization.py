"""Tests for error message sanitization (issue #42).

Verifies that raw HTTP error bodies from LLM providers are:
- Logged server-side (via the ``logging`` module)
- Stripped from exception messages and ``arbiter_error`` fields
  returned to API clients
"""

import logging

from loom_ai.consensus import ConsensusEngine, _strip_response_body
from loom_ai.models import ChatMessage, ChatResponse

# ── _strip_response_body unit tests ─────────────────────────────────


def test_strip_body_from_chat_error():
    msg = (
        "LLM API error 429 from https://api.example.com/v1: "
        '{"error":{"message":"Rate limit exceeded","type":"rate_limit"}}'
    )
    assert _strip_response_body(msg) == (
        "LLM API error 429 from https://api.example.com/v1"
    )


def test_strip_body_containing_api_key():
    msg = (
        "LLM API error 401 from https://api.openai.com/v1: "
        '{"error":{"message":"Invalid API key: sk-proj-abc123..."}}'
    )
    assert _strip_response_body(msg) == (
        "LLM API error 401 from https://api.openai.com/v1"
    )


def test_strip_body_from_list_models_error():
    msg = (
        "Failed to list models from https://api.example.com/v1: 403 "
        '{"error":"Forbidden","details":"key expired"}'
    )
    assert _strip_response_body(msg) == (
        "Failed to list models from https://api.example.com/v1: 403"
    )


def test_strip_preserves_safe_messages():
    safe = "Arbiter call failed after retries"
    assert _strip_response_body(safe) == safe


def test_strip_preserves_connection_errors():
    msg = "LLM API connection error to https://api.example.com: Connection refused"
    assert _strip_response_body(msg) == msg


def test_strip_handles_html_body():
    msg = (
        "LLM API error 502 from https://proxy.example.com: "
        "<html><body>Bad Gateway</body></html>"
    )
    assert _strip_response_body(msg) == (
        "LLM API error 502 from https://proxy.example.com"
    )


# ── _sanitize_error unit tests ──────────────────────────────────────


def test_sanitize_error_strips_body():
    inner = RuntimeError(
        "LLM API error 500 from https://api.example.com/v1: "
        '{"error":"internal","secret":"sk-1234"}'
    )
    outer = RuntimeError("Arbiter call failed after retries")
    outer.__cause__ = inner
    result = ConsensusEngine._sanitize_error(outer)
    assert result == "RuntimeError: Arbiter call failed after retries"
    assert "sk-1234" not in result


def test_sanitize_error_plain_message():
    exc = RuntimeError("Model model-x unavailable")
    result = ConsensusEngine._sanitize_error(exc)
    assert result == "RuntimeError: Model model-x unavailable"


def test_sanitize_error_with_leaked_body():
    exc = RuntimeError(
        "LLM API error 401 from https://api.openai.com/v1: "
        '{"error":{"message":"Incorrect API key provided: sk-abc..."}}'
    )
    result = ConsensusEngine._sanitize_error(exc)
    assert "sk-abc" not in result
    assert result == "RuntimeError: LLM API error 401 from https://api.openai.com/v1"


# ── Integration: synthesize returns sanitized arbiter_error ─────────


class LeakyArbiterBackend:
    """Backend that raises errors with fake sensitive data in the body."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if model == "arbiter":
            raise RuntimeError(
                "LLM API error 401 from https://api.openai.com/v1: "
                '{"error":{"message":"Invalid API key: sk-secret-key-12345"}}'
            )
        return ChatResponse(
            content=f"Response from {model}",
            model=model or "default",
            provider="fake",
            usage={"total_tokens": 10},
        )

    async def chat_stream(self, messages, **kwargs):
        if False:
            yield "unused"

    async def list_models(self) -> list[str]:
        return ["worker"]


async def test_synthesize_does_not_leak_error_body():
    engine = ConsensusEngine(LeakyArbiterBackend(), retries=0)
    result = await engine.synthesize(
        "test prompt",
        ["worker"],
        arbiter_model="arbiter",
    )
    assert result.arbiter_attempted is True
    assert result.arbiter_error is not None
    # The raw error body must not appear in arbiter_error
    assert "sk-secret-key-12345" not in result.arbiter_error
    assert "Invalid API key" not in result.arbiter_error
    # The sanitized error should still indicate the failure type
    assert "RuntimeError" in result.arbiter_error
    assert "Arbiter call failed" in result.arbiter_error


async def test_synthesize_logs_full_error(caplog):
    engine = ConsensusEngine(LeakyArbiterBackend(), retries=0)
    with caplog.at_level(logging.WARNING, logger="loom_ai.consensus"):
        result = await engine.synthesize(
            "test prompt",
            ["worker"],
            arbiter_model="arbiter",
        )
    assert result.arbiter_attempted is True
    # The full error should be logged server-side
    assert any("Arbiter synthesis failed" in r.message for r in caplog.records)


# ── Backwards-compatible: existing arbiter_error format unchanged ───


class SimpleFailureBackend:
    """Backend where arbiter simply raises a plain RuntimeError."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if model == "arbiter":
            raise RuntimeError("arbiter unavailable")
        return ChatResponse(
            content=f"response from {model}",
            model=model or "default",
        )

    async def chat_stream(self, messages, **kwargs):
        if False:
            yield "unused"

    async def list_models(self) -> list[str]:
        return ["worker"]


async def test_arbiter_error_format_unchanged_for_safe_errors():
    engine = ConsensusEngine(SimpleFailureBackend(), retries=0)
    result = await engine.synthesize(
        "test",
        ["worker"],
        arbiter_model="arbiter",
    )
    assert result.arbiter_error == "RuntimeError: Arbiter call failed after retries"
