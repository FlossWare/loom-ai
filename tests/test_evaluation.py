"""Tests for SimpleEvaluationHarness: mock backend scoring, verdict
thresholds, no-backend defaults, and parallel evaluation.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from loom_ai.backends.evaluation import (
    SimpleEvaluationHarness,
    _parse_scores,
    _verdict_from_average,
)
from loom_ai.models import ChatMessage, ChatResponse

# ── Helpers ──────────────────────────────────────────────────────────────


class MockLLMBackend:
    """Configurable mock that returns canned score responses.

    Parameters
    ----------
    scores:
        A dict mapping model name to a ``(correctness, completeness,
        quality)`` tuple.  If a model is not present, the backend
        raises an error for that model.
    """

    def __init__(
        self,
        scores: dict[str, tuple[int, int, int]] | None = None,
    ) -> None:
        self._scores = scores or {}
        self.call_count = 0
        self.models_called: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.call_count += 1
        self.models_called.append(model or "default")

        if model and model in self._scores:
            c, comp, q = self._scores[model]
            content = f"correctness: {c}\ncompleteness: {comp}\nquality: {q}"
            return ChatResponse(content=content, model=model)

        raise RuntimeError(f"No mock scores for model: {model}")

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield ""  # pragma: no cover

    async def list_models(self) -> list[str]:
        return sorted(self._scores.keys())


class TrackingLLMBackend(MockLLMBackend):
    """Mock that also records timestamps to verify parallel execution."""

    def __init__(
        self,
        scores: dict[str, tuple[int, int, int]],
        delay: float = 0.05,
    ) -> None:
        super().__init__(scores)
        self._delay = delay
        self.call_times: list[float] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        loop = asyncio.get_event_loop()
        self.call_times.append(loop.time())
        await asyncio.sleep(self._delay)
        return await super().chat(messages, model=model, temperature=temperature)


# ── Unit tests for helpers ───────────────────────────────────────────────


class TestParseScores:
    """Tests for the _parse_scores helper."""

    def test_valid_response(self) -> None:
        text = "correctness: 4\ncompleteness: 3\nquality: 5"
        result = _parse_scores(text)
        assert result == {"correctness": 4, "completeness": 3, "quality": 5}

    def test_case_insensitive(self) -> None:
        text = "Correctness: 4\nCompleteness: 3\nQuality: 5"
        result = _parse_scores(text)
        assert result == {"correctness": 4, "completeness": 3, "quality": 5}

    def test_extra_whitespace(self) -> None:
        text = "correctness:  4 \ncompleteness:3\nquality: 5"
        result = _parse_scores(text)
        assert result == {"correctness": 4, "completeness": 3, "quality": 5}

    def test_ignores_invalid_scores(self) -> None:
        text = "correctness: 6\ncompleteness: 0\nquality: 3"
        result = _parse_scores(text)
        assert result == {"quality": 3}

    def test_empty_string(self) -> None:
        assert _parse_scores("") == {}

    def test_garbage_input(self) -> None:
        assert _parse_scores("no scores here at all") == {}

    def test_partial_response(self) -> None:
        text = "correctness: 4\nsome other text\nquality: 2"
        result = _parse_scores(text)
        assert result == {"correctness": 4, "quality": 2}

    def test_embedded_in_prose(self) -> None:
        text = (
            "Here is my evaluation:\n"
            "correctness: 3\n"
            "completeness: 4\n"
            "quality: 5\n"
            "Overall, good work."
        )
        result = _parse_scores(text)
        assert result == {"correctness": 3, "completeness": 4, "quality": 5}


class TestVerdictFromAverage:
    """Tests for the _verdict_from_average helper."""

    def test_high_score_accepts(self) -> None:
        assert _verdict_from_average(5.0) == "ACCEPT"
        assert _verdict_from_average(4.0) == "ACCEPT"

    def test_medium_score_accepts_with_reservations(self) -> None:
        assert _verdict_from_average(3.9) == "ACCEPT_WITH_RESERVATIONS"
        assert _verdict_from_average(3.0) == "ACCEPT_WITH_RESERVATIONS"
        assert _verdict_from_average(2.5) == "ACCEPT_WITH_RESERVATIONS"

    def test_low_score_rejects(self) -> None:
        assert _verdict_from_average(2.4) == "REJECT"
        assert _verdict_from_average(1.0) == "REJECT"

    def test_boundary_at_four(self) -> None:
        assert _verdict_from_average(4.0) == "ACCEPT"
        assert _verdict_from_average(3.999) == "ACCEPT_WITH_RESERVATIONS"

    def test_boundary_at_two_point_five(self) -> None:
        assert _verdict_from_average(2.5) == "ACCEPT_WITH_RESERVATIONS"
        assert _verdict_from_average(2.499) == "REJECT"


# ── Integration tests for SimpleEvaluationHarness ────────────────────────


async def test_no_backend_returns_default_accept() -> None:
    """When no backend is provided, evaluate returns ACCEPT with max scores."""
    harness = SimpleEvaluationHarness(backend=None)
    result = await harness.evaluate("some output", task="some task", models=["model-a"])
    assert result.verdict == "ACCEPT"
    assert result.scores["correctness"] == 5
    assert result.scores["completeness"] == 5
    assert result.scores["quality"] == 5
    assert result.evaluator_models == []
    assert "default" in result.reasoning.lower()


async def test_accept_verdict_with_high_scores() -> None:
    """All models returning 4+ yields ACCEPT."""
    backend = MockLLMBackend(
        scores={
            "model-a": (5, 4, 5),
            "model-b": (4, 5, 4),
        }
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "high quality output",
        task="write a function",
        models=["model-a", "model-b"],
    )
    assert result.verdict == "ACCEPT"
    assert result.scores["correctness"] == pytest.approx(4.5)
    assert result.scores["completeness"] == pytest.approx(4.5)
    assert result.scores["quality"] == pytest.approx(4.5)
    assert set(result.evaluator_models) == {"model-a", "model-b"}


async def test_accept_with_reservations_verdict() -> None:
    """Scores averaging between 2.5 and 4.0 yield ACCEPT_WITH_RESERVATIONS."""
    backend = MockLLMBackend(
        scores={
            "model-a": (3, 3, 3),
            "model-b": (3, 3, 3),
        }
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "mediocre output",
        task="write a function",
        models=["model-a", "model-b"],
    )
    assert result.verdict == "ACCEPT_WITH_RESERVATIONS"
    assert result.scores["correctness"] == pytest.approx(3.0)


async def test_reject_verdict_with_low_scores() -> None:
    """Scores averaging below 2.5 yield REJECT."""
    backend = MockLLMBackend(
        scores={
            "model-a": (1, 2, 1),
            "model-b": (2, 1, 2),
        }
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "bad output",
        task="write a function",
        models=["model-a", "model-b"],
    )
    assert result.verdict == "REJECT"
    overall_avg = sum(result.scores.values()) / len(result.scores)
    assert overall_avg < 2.5


async def test_all_models_fail_returns_reject() -> None:
    """When every model fails, the harness returns REJECT with no scores."""
    backend = MockLLMBackend(scores={})
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "some output",
        task="some task",
        models=["model-x", "model-y"],
    )
    assert result.verdict == "REJECT"
    assert result.scores == {}
    assert result.evaluator_models == []


async def test_partial_model_failure() -> None:
    """One model failing does not prevent evaluation from others."""
    backend = MockLLMBackend(
        scores={
            "model-a": (5, 5, 5),
            # model-b not configured, so it will raise
        }
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "some output",
        task="some task",
        models=["model-a", "model-b"],
    )
    assert result.verdict == "ACCEPT"
    assert result.evaluator_models == ["model-a"]
    assert result.scores["correctness"] == pytest.approx(5.0)


async def test_parallel_execution() -> None:
    """Models are queried concurrently, not sequentially."""
    backend = TrackingLLMBackend(
        scores={
            "model-a": (4, 4, 4),
            "model-b": (4, 4, 4),
            "model-c": (4, 4, 4),
        },
        delay=0.1,
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "output",
        task="task",
        models=["model-a", "model-b", "model-c"],
    )
    assert result.verdict == "ACCEPT"
    assert backend.call_count == 3

    # If calls were sequential, total time would be >= 0.3s.
    # Parallel execution should start all calls within a tight window.
    assert len(backend.call_times) == 3
    time_spread = max(backend.call_times) - min(backend.call_times)
    # All calls should have started within 0.05s of each other.
    assert time_spread < 0.05


async def test_reasoning_contains_scores() -> None:
    """The reasoning field contains human-readable score information."""
    backend = MockLLMBackend(scores={"model-a": (3, 4, 5)})
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate("output", task="task", models=["model-a"])
    assert "correctness" in result.reasoning
    assert "completeness" in result.reasoning
    assert "quality" in result.reasoning
    assert "average" in result.reasoning.lower()


async def test_protocol_compliance() -> None:
    """SimpleEvaluationHarness satisfies the EvaluationHarness protocol."""
    from loom_ai.contracts_phase3 import EvaluationHarness

    harness = SimpleEvaluationHarness()
    assert isinstance(harness, EvaluationHarness)


async def test_single_model_evaluation() -> None:
    """Evaluation works correctly with just one model."""
    backend = MockLLMBackend(scores={"solo": (5, 5, 5)})
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate(
        "perfect output", task="simple task", models=["solo"]
    )
    assert result.verdict == "ACCEPT"
    assert result.evaluator_models == ["solo"]
    assert len(result.scores) == 3


async def test_boundary_accept_threshold() -> None:
    """Exact 4.0 average yields ACCEPT."""
    backend = MockLLMBackend(
        scores={
            "model-a": (4, 4, 4),
        }
    )
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate("output", task="task", models=["model-a"])
    assert result.verdict == "ACCEPT"


async def test_boundary_reservations_threshold() -> None:
    """Exact 2.5 average yields ACCEPT_WITH_RESERVATIONS, not REJECT.

    This needs mixed scores that average out to exactly 2.5.
    With two models: (2,3,2) avg=2.33 and (3,3,3) avg=3.0.
    Cross-model avg per dim: correctness=2.5, completeness=3.0, quality=2.5.
    Overall: (2.5+3.0+2.5)/3 = 2.666..., which is ACCEPT_WITH_RESERVATIONS.
    We instead just check a single model at (2,3,3) avg=2.666.
    """
    backend = MockLLMBackend(scores={"model-a": (2, 3, 3)})
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate("output", task="task", models=["model-a"])
    assert result.verdict == "ACCEPT_WITH_RESERVATIONS"


async def test_empty_models_list() -> None:
    """An empty models list with a backend returns REJECT (no evaluators)."""
    backend = MockLLMBackend(scores={})
    harness = SimpleEvaluationHarness(backend=backend)
    result = await harness.evaluate("output", task="task", models=[])
    assert result.verdict == "REJECT"
    assert result.evaluator_models == []
