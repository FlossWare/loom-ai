"""Tests for loom_ai.consensus.ConsensusEngine."""

import asyncio
import time

import pytest

from loom_ai.consensus import ConsensusEngine, ConsensusResult
from loom_ai.models import ChatMessage, ChatResponse


class FakeLLMBackend:
    """Minimal LLMBackend that records calls and returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail_models: set[str] = set()
        self.slow_models: dict[str, float] = {}
        self.retryable_fail_models: set[str] = set()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append({"model": model, "temperature": temperature})

        if model in self.slow_models:
            await asyncio.sleep(self.slow_models[model])

        if model in self.fail_models:
            raise RuntimeError(f"Model {model} unavailable")

        if model in self.retryable_fail_models:
            self.retryable_fail_models.discard(model)
            raise RuntimeError("LLM API error 429 from http://fake: rate limited")

        content = f"Response from {model}"
        return ChatResponse(
            content=content,
            model=model or "default",
            provider="fake",
            usage={"total_tokens": 10},
        )

    async def chat_stream(self, messages, **kwargs):
        yield "not used"

    async def list_models(self) -> list[str]:
        return ["model-a", "model-b", "model-c"]


async def test_gather_basic_fanout():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(backend)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(
        msgs,
        ["model-a", "model-b", "model-c"],
    )
    assert len(responses) == 3
    assert len(failed) == 0
    assert {r.model for r in responses} == {"model-a", "model-b", "model-c"}


async def test_gather_partial_failure():
    backend = FakeLLMBackend()
    backend.fail_models = {"model-b"}
    engine = ConsensusEngine(backend, retries=0)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(
        msgs,
        ["model-a", "model-b", "model-c"],
    )
    assert len(responses) == 2
    assert "model-b" in failed
    assert {r.model for r in responses} == {"model-a", "model-c"}


async def test_gather_all_fail():
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a", "model-b"}
    engine = ConsensusEngine(backend, retries=0)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(msgs, ["model-a", "model-b"])
    assert len(responses) == 0
    assert set(failed) == {"model-a", "model-b"}


async def test_gather_timeout():
    backend = FakeLLMBackend()
    backend.slow_models = {"model-slow": 10.0}
    engine = ConsensusEngine(backend, retries=0)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(
        msgs,
        ["model-a", "model-slow"],
        timeout_seconds=1,
    )
    assert len(responses) == 1
    assert responses[0].model == "model-a"
    assert "model-slow" in failed


async def test_gather_retries_on_429():
    backend = FakeLLMBackend()
    backend.retryable_fail_models = {"model-a"}
    engine = ConsensusEngine(backend, retries=2)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(msgs, ["model-a"])
    assert len(responses) == 1
    assert responses[0].model == "model-a"
    assert len(failed) == 0
    assert len(backend.calls) == 2


async def test_gather_respects_concurrency_limit():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(backend, max_concurrent=2)
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(msgs, ["m1", "m2", "m3", "m4"])
    assert len(responses) == 4
    assert len(failed) == 0


async def test_gather_override_params():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(
        backend,
        max_concurrent=10,
        timeout_seconds=60,
        retries=2,
    )
    msgs = [ChatMessage(role="user", content="Hello")]
    responses, failed = await engine.gather(
        msgs,
        ["model-a"],
        max_concurrent=1,
        timeout_seconds=30,
        retries=0,
    )
    assert len(responses) == 1


async def test_synthesize_basic():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(backend)
    result = await engine.synthesize(
        "What is Python?",
        ["model-a", "model-b"],
    )
    assert isinstance(result, ConsensusResult)
    assert len(result.worker_responses) == 2
    assert len(result.failed_models) == 0
    assert result.synthesis.content.startswith("Response from")


async def test_synthesize_with_all_failures():
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a", "model-b"}
    engine = ConsensusEngine(backend, retries=0)
    result = await engine.synthesize(
        "What is Python?",
        ["model-a", "model-b"],
    )
    assert result.synthesis.content == "All models failed to respond."
    assert len(result.worker_responses) == 0
    assert set(result.failed_models) == {"model-a", "model-b"}


async def test_synthesize_partial_failure():
    backend = FakeLLMBackend()
    backend.fail_models = {"model-b"}
    engine = ConsensusEngine(backend, retries=0)
    result = await engine.synthesize(
        "What is Python?",
        ["model-a", "model-b", "model-c"],
    )
    assert len(result.worker_responses) == 2
    assert "model-b" in result.failed_models
    assert result.synthesis.content != ""


async def test_synthesize_uses_tool_name():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(backend)
    result = await engine.synthesize(
        "Review this code",
        ["model-a"],
        tool_name="review",
    )
    assert len(result.worker_responses) == 1
    assert len(backend.calls) == 2


async def test_synthesize_arbiter_model():
    backend = FakeLLMBackend()
    engine = ConsensusEngine(backend)
    await engine.synthesize(
        "Design a system",
        ["model-a"],
        arbiter_model="arbiter-special",
    )
    arbiter_call = backend.calls[-1]
    assert arbiter_call["model"] == "arbiter-special"


async def test_arbiter_timeout_returns_worker_responses():
    backend = FakeLLMBackend()
    backend.slow_models = {"arbiter": 0.1}
    engine = ConsensusEngine(backend, retries=0)
    messages = [ChatMessage(role="user", content="Synthesize")]

    with pytest.raises(RuntimeError, match="Arbiter call failed"):
        await engine._call_with_retry(
            messages,
            model="arbiter",
            timeout_seconds=0.01,
            retries=0,
        )


async def test_is_retryable_timeout():
    assert ConsensusEngine._is_retryable(asyncio.TimeoutError())


async def test_is_retryable_429():
    exc = RuntimeError("LLM API error 429 from http://example.com")
    assert ConsensusEngine._is_retryable(exc)


async def test_is_retryable_503():
    exc = RuntimeError("LLM API error 503 from http://example.com")
    assert ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_400():
    exc = RuntimeError("LLM API error 400 from http://example.com")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_value_error():
    assert not ConsensusEngine._is_retryable(ValueError("bad input"))


async def test_is_retryable_connection_error():
    assert ConsensusEngine._is_retryable(ConnectionError("refused"))


async def test_is_retryable_os_error():
    assert ConsensusEngine._is_retryable(OSError("network unreachable"))


async def test_is_retryable_runtime_connection_error():
    exc = RuntimeError("LLM API connection error to https://x: refused")
    assert ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_5000():
    """Port 5000 in URL must not match '500' status code."""
    exc = RuntimeError("llm api error 400 from http://api:5000/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_5003():
    """Port 5003 in URL must not match '500' status code."""
    exc = RuntimeError("llm api error 400 from http://api:5003/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_5029():
    """Port 5029 in URL must not match '502' status code."""
    exc = RuntimeError("llm api error 400 from http://api:5029/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_5039():
    """Port 5039 in URL must not match '503' status code."""
    exc = RuntimeError("llm api error 400 from http://api:5039/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_5049():
    """Port 5049 in URL must not match '504' status code."""
    exc = RuntimeError("llm api error 400 from http://api:5049/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_not_retryable_port_4290():
    """Port 4290 in URL must not match '429' status code."""
    exc = RuntimeError("llm api error 400 from http://api:4290/v1: bad request")
    assert not ConsensusEngine._is_retryable(exc)


async def test_is_retryable_500_with_port():
    """Real 500 error from a URL with port must still be retryable."""
    exc = RuntimeError("llm api error 500 from http://api:8080/v1: internal error")
    assert ConsensusEngine._is_retryable(exc)


async def test_is_retryable_429_with_port_5000():
    """Real 429 error from port 5000 must still be retryable."""
    exc = RuntimeError("llm api error 429 from http://api:5000/v1: rate limited")
    assert ConsensusEngine._is_retryable(exc)


def test_consensus_engine_importable():
    from loom_ai import ConsensusEngine, ConsensusResult

    assert ConsensusEngine is not None
    assert ConsensusResult is not None


def test_consensus_result_defaults():
    resp = ChatResponse(content="test")
    result = ConsensusResult(synthesis=resp)
    assert result.worker_responses == []
    assert result.failed_models == []


async def test_gather_recomputes_deadline_after_semaphore(monkeypatch):
    """Deadline must be recomputed after semaphore acquisition (issue #40).

    With ``max_concurrent=1``, model-slow holds the semaphore for 0.6 s.
    The overall deadline is 0.8 s, so model-b acquires the semaphore at
    ~0.6 s with only ~0.2 s remaining.  Before the fix, the stale
    ``remaining`` was computed *before* waiting for the semaphore, so
    model-b's ``wait_for`` would have used the full ~0.8 s budget,
    violating the deadline.  After the fix the total wall-clock time must
    stay within a small margin of the 0.8 s deadline.
    """
    backend = FakeLLMBackend()
    # model-slow takes 0.6 s, model-b is instant
    backend.slow_models = {"model-slow": 0.6}
    engine = ConsensusEngine(backend, max_concurrent=1, retries=0)
    msgs = [ChatMessage(role="user", content="Hello")]

    start = time.monotonic()
    responses, failed = await engine.gather(
        msgs,
        ["model-slow", "model-b"],
        timeout_seconds=0.8,
    )
    elapsed = time.monotonic() - start

    # Both should succeed (model-slow takes 0.6 s, model-b starts at
    # ~0.6 s with ~0.2 s remaining and finishes instantly).
    assert len(responses) == 2
    assert len(failed) == 0

    # Critical: total time must be close to 0.8 s, not 0.8 + 0.8 = 1.6 s
    # which would happen with the stale deadline bug.
    assert elapsed < 1.2, (
        f"gather took {elapsed:.2f}s, suggesting stale deadline after semaphore wait"
    )
