"""Tests for loom_ai.backends.patterns execution patterns."""

import pytest

from loom_ai.backends.patterns import (
    CascadePattern,
    ConsensusPattern,
    MapReducePattern,
)
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.models_phase1 import PatternResult

# ── Fake backends ────────────────────────────────────────────────────────


class FakeLLMBackend:
    """Minimal LLMBackend that returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail_models: set[str] = set()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append({"model": model, "messages": messages})

        if model in self.fail_models:
            raise RuntimeError(f"Model {model} unavailable")

        return ChatResponse(
            content=f"Response from {model}",
            model=model or "default",
            provider="fake",
        )

    async def chat_stream(self, messages, **kwargs):
        yield "not used"

    async def list_models(self) -> list[str]:
        return ["model-a", "model-b", "model-c"]


class FakeRouter:
    """Minimal ModelRouter that wraps a FakeLLMBackend per model."""

    def __init__(self, backend: FakeLLMBackend) -> None:
        self._backend = backend

    async def route(self, model: str, *, fallback: bool = True):
        """Return a one-model backend wrapper."""
        return _SingleModelBackend(self._backend, model)


class _SingleModelBackend:
    """Backend that always calls the underlying backend without model=."""

    def __init__(self, backend: FakeLLMBackend, model: str) -> None:
        self._backend = backend
        self._model = model

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        # Route calls through the real backend with the intended model.
        return await self._backend.chat(messages, model=self._model)

    async def chat_stream(self, messages, **kwargs):
        yield "not used"

    async def list_models(self) -> list[str]:
        return [self._model]


# ── ConsensusPattern ─────────────────────────────────────────────────────


async def test_consensus_basic():
    """ConsensusPattern fans out to all models and collects results."""
    backend = FakeLLMBackend()
    pattern = ConsensusPattern()

    result = await pattern.execute(
        "What is Python?",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert isinstance(result, PatternResult)
    assert result.pattern == "consensus"
    assert len(result.results) == 3
    assert result.metadata["total"] == 3
    assert result.metadata["succeeded"] == 3
    assert result.metadata["failed"] == 0
    assert result.metadata["consensus"] != ""


async def test_consensus_most_common_answer():
    """ConsensusPattern picks the most common response."""

    class DuplicatingBackend:
        async def chat(self, messages, *, model=None, **kwargs):
            # Two models return the same answer.
            if model in ("model-a", "model-c"):
                return ChatResponse(content="42", model=model or "")
            return ChatResponse(content="43", model=model or "")

        async def chat_stream(self, messages, **kwargs):
            yield "not used"

        async def list_models(self):
            return []

    pattern = ConsensusPattern()
    result = await pattern.execute(
        "answer",
        models=["model-a", "model-b", "model-c"],
        backend=DuplicatingBackend(),
    )

    assert result.metadata["consensus"] == "42"


async def test_consensus_partial_failure():
    """ConsensusPattern handles partial model failures gracefully."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-b"}
    pattern = ConsensusPattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert result.metadata["succeeded"] == 2
    assert result.metadata["failed"] == 1
    failed_results = [r for r in result.results if not r.get("success")]
    assert len(failed_results) == 1
    assert failed_results[0]["model"] == "model-b"


async def test_consensus_all_fail():
    """ConsensusPattern returns empty consensus when all models fail."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a", "model-b"}
    pattern = ConsensusPattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b"],
        backend=backend,
    )

    assert result.metadata["succeeded"] == 0
    assert result.metadata["consensus"] == ""


async def test_consensus_with_router():
    """ConsensusPattern works when given a router instead of a backend."""
    backend = FakeLLMBackend()
    router = FakeRouter(backend)
    pattern = ConsensusPattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b"],
        router=router,
    )

    assert result.metadata["succeeded"] == 2
    assert len(result.results) == 2


# ── CascadePattern ───────────────────────────────────────────────────────


async def test_cascade_first_succeeds():
    """CascadePattern returns the first model's response when it succeeds."""
    backend = FakeLLMBackend()
    pattern = CascadePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert result.pattern == "cascade"
    assert len(result.results) == 1
    assert result.results[0]["model"] == "model-a"
    assert result.metadata["model_used"] == "model-a"
    assert result.metadata["attempts"] == 1
    # Only the first model should have been called.
    assert len(backend.calls) == 1


async def test_cascade_falls_through():
    """CascadePattern tries the next model when the first fails."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a", "model-b"}
    pattern = CascadePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert result.metadata["model_used"] == "model-c"
    assert result.metadata["attempts"] == 3
    assert len(result.metadata["errors"]) == 2
    assert result.results[0]["content"] == "Response from model-c"


async def test_cascade_all_fail():
    """CascadePattern returns empty results when every model fails."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a", "model-b"}
    pattern = CascadePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b"],
        backend=backend,
    )

    assert result.results == []
    assert result.metadata["model_used"] is None
    assert len(result.metadata["errors"]) == 2


async def test_cascade_with_router():
    """CascadePattern works when given a router."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-a"}
    router = FakeRouter(backend)
    pattern = CascadePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b"],
        router=router,
    )

    assert result.metadata["model_used"] == "model-b"


# ── MapReducePattern ─────────────────────────────────────────────────────


async def test_map_reduce_collects_all():
    """MapReducePattern collects responses from all models."""
    backend = FakeLLMBackend()
    pattern = MapReducePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert result.pattern == "map_reduce"
    assert len(result.results) == 3
    assert result.metadata["succeeded"] == 3
    assert "Response from model-a" in result.metadata["combined"]
    assert "Response from model-b" in result.metadata["combined"]
    assert "Response from model-c" in result.metadata["combined"]


async def test_map_reduce_custom_prompt():
    """MapReducePattern uses config['map_prompt'] when provided."""
    backend = FakeLLMBackend()
    pattern = MapReducePattern()

    await pattern.execute(
        "original task",
        models=["model-a"],
        backend=backend,
        config={"map_prompt": "custom prompt"},
    )

    # The backend should have received the custom prompt.
    sent_content = backend.calls[0]["messages"][0].content
    assert sent_content == "custom prompt"


async def test_map_reduce_partial_failure():
    """MapReducePattern handles partial failures and still combines."""
    backend = FakeLLMBackend()
    backend.fail_models = {"model-b"}
    pattern = MapReducePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b", "model-c"],
        backend=backend,
    )

    assert result.metadata["succeeded"] == 2
    assert result.metadata["failed"] == 1
    assert "Response from model-b" not in result.metadata["combined"]


async def test_map_reduce_with_router():
    """MapReducePattern works when given a router."""
    backend = FakeLLMBackend()
    router = FakeRouter(backend)
    pattern = MapReducePattern()

    result = await pattern.execute(
        "task",
        models=["model-a", "model-b"],
        router=router,
    )

    assert result.metadata["succeeded"] == 2


# ── Shared behavior ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern_cls",
    [ConsensusPattern, CascadePattern, MapReducePattern],
)
async def test_duration_ms_is_recorded(pattern_cls):
    """Every pattern records a positive duration_ms."""
    backend = FakeLLMBackend()
    pattern = pattern_cls()

    result = await pattern.execute(
        "task",
        models=["model-a"],
        backend=backend,
    )

    assert result.duration_ms > 0


@pytest.mark.parametrize(
    "pattern_cls",
    [ConsensusPattern, CascadePattern, MapReducePattern],
)
async def test_requires_router_or_backend(pattern_cls):
    """Patterns raise ValueError when neither router nor backend given."""
    pattern = pattern_cls()

    with pytest.raises(ValueError, match="router or backend"):
        await pattern.execute(
            "task",
            models=["model-a"],
        )


def test_patterns_importable():
    """Patterns are importable from the backends package."""
    from loom_ai.backends.patterns import (
        CascadePattern,
        ConsensusPattern,
        MapReducePattern,
    )

    assert ConsensusPattern is not None
    assert CascadePattern is not None
    assert MapReducePattern is not None


def test_patterns_satisfy_protocol():
    """Pattern classes satisfy the ExecutionPattern protocol."""
    from loom_ai.contracts_phase1 import ExecutionPattern

    assert isinstance(ConsensusPattern(), ExecutionPattern)
    assert isinstance(CascadePattern(), ExecutionPattern)
    assert isinstance(MapReducePattern(), ExecutionPattern)
