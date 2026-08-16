"""Tests for the Thompson Sampling strategy selector backend."""

import random

import pytest

from loom_ai.backends.strategy import ThompsonSamplingSelector
from loom_ai.contracts_phase2 import StrategySelector
from loom_ai.models_phase2 import StrategyStats

# -- Protocol conformance ----------------------------------------------------


def test_satisfies_protocol():
    """ThompsonSamplingSelector satisfies the StrategySelector protocol."""
    assert isinstance(ThompsonSamplingSelector(), StrategySelector)


# -- select ------------------------------------------------------------------


async def test_select_returns_candidate():
    """select always returns one of the provided candidates."""
    selector = ThompsonSamplingSelector()
    result = await selector.select("code", candidates=["a", "b", "c"])
    assert result in {"a", "b", "c"}


async def test_select_single_candidate():
    """With a single candidate, select always returns it."""
    selector = ThompsonSamplingSelector()
    for _ in range(10):
        result = await selector.select("code", candidates=["only"])
        assert result == "only"


async def test_select_empty_candidates_raises():
    """select raises ValueError when candidates list is empty."""
    selector = ThompsonSamplingSelector()
    with pytest.raises(ValueError, match="candidates must not be empty"):
        await selector.select("code", candidates=[])


async def test_select_favors_rewarded_strategy():
    """After many positive rewards, the rewarded strategy is selected
    more often than unrewarded ones."""
    selector = ThompsonSamplingSelector()

    # Give "fast" many successes
    for _ in range(50):
        await selector.update("fast", "code", reward=1.0)

    # Give "slow" many failures
    for _ in range(50):
        await selector.update("slow", "code", reward=0.0)

    # Sample many times and check distribution
    counts: dict[str, int] = {"fast": 0, "slow": 0}
    for _ in range(200):
        choice = await selector.select("code", candidates=["fast", "slow"])
        counts[choice] += 1

    # "fast" should be chosen far more often
    assert counts["fast"] > counts["slow"]


async def test_select_deterministic_with_seed():
    """With a fixed random seed, select is reproducible."""
    selector = ThompsonSamplingSelector()
    selector._rng = random.Random(42)
    first = await selector.select("code", candidates=["a", "b", "c"])

    selector2 = ThompsonSamplingSelector()
    selector2._rng = random.Random(42)
    second = await selector2.select("code", candidates=["a", "b", "c"])

    assert first == second


# -- update ------------------------------------------------------------------


async def test_update_increments_alpha_on_high_reward():
    """Reward > 0.5 increments alpha (success count)."""
    selector = ThompsonSamplingSelector()

    await selector.update("greedy", "code", reward=0.9)

    stats = await selector.performance()
    s = stats["greedy:code"]
    assert s.alpha == 2.0  # 1.0 (prior) + 1.0
    assert s.beta == 1.0  # unchanged
    assert s.successes == 1
    assert s.total_trials == 1


async def test_update_increments_beta_on_low_reward():
    """Reward <= 0.5 increments beta (failure count)."""
    selector = ThompsonSamplingSelector()

    await selector.update("greedy", "code", reward=0.3)

    stats = await selector.performance()
    s = stats["greedy:code"]
    assert s.alpha == 1.0  # unchanged
    assert s.beta == 2.0  # 1.0 (prior) + 1.0
    assert s.successes == 0
    assert s.total_trials == 1


async def test_update_boundary_reward():
    """Reward exactly 0.5 is treated as failure (increments beta)."""
    selector = ThompsonSamplingSelector()

    await selector.update("edge", "code", reward=0.5)

    stats = await selector.performance()
    s = stats["edge:code"]
    assert s.alpha == 1.0
    assert s.beta == 2.0
    assert s.successes == 0


async def test_update_tracks_avg_reward():
    """Average reward is computed correctly over multiple updates."""
    selector = ThompsonSamplingSelector()

    await selector.update("s1", "code", reward=1.0)
    await selector.update("s1", "code", reward=0.0)
    await selector.update("s1", "code", reward=0.5)

    stats = await selector.performance()
    s = stats["s1:code"]
    assert s.total_trials == 3
    assert abs(s.avg_reward - 0.5) < 1e-9


async def test_update_multiple_strategies():
    """Different strategies maintain independent bandit state."""
    selector = ThompsonSamplingSelector()

    await selector.update("a", "code", reward=1.0)
    await selector.update("b", "code", reward=0.0)

    stats = await selector.performance()
    assert stats["a:code"].successes == 1
    assert stats["a:code"].alpha == 2.0
    assert stats["b:code"].successes == 0
    assert stats["b:code"].beta == 2.0


async def test_update_multiple_task_types():
    """Same strategy with different task types maintains independent state."""
    selector = ThompsonSamplingSelector()

    await selector.update("greedy", "code", reward=1.0)
    await selector.update("greedy", "review", reward=0.0)

    stats = await selector.performance()
    assert stats["greedy:code"].successes == 1
    assert stats["greedy:code"].alpha == 2.0
    assert stats["greedy:review"].successes == 0
    assert stats["greedy:review"].beta == 2.0


# -- performance -------------------------------------------------------------


async def test_performance_empty():
    """performance returns an empty dict when no arms exist."""
    selector = ThompsonSamplingSelector()
    stats = await selector.performance()
    assert stats == {}


async def test_performance_returns_strategy_stats():
    """performance returns StrategyStats dataclass instances."""
    selector = ThompsonSamplingSelector()
    await selector.update("s1", "code", reward=0.8)

    stats = await selector.performance()
    assert len(stats) == 1
    s = stats["s1:code"]
    assert isinstance(s, StrategyStats)
    assert s.strategy == "s1"
    assert s.task_type == "code"


async def test_performance_filter_by_task_type():
    """performance with task_type filter returns only matching arms."""
    selector = ThompsonSamplingSelector()

    await selector.update("a", "code", reward=1.0)
    await selector.update("b", "review", reward=0.0)
    await selector.update("c", "code", reward=0.5)

    code_stats = await selector.performance(task_type="code")
    assert len(code_stats) == 2
    assert "a:code" in code_stats
    assert "c:code" in code_stats
    assert "b:review" not in code_stats

    review_stats = await selector.performance(task_type="review")
    assert len(review_stats) == 1
    assert "b:review" in review_stats


async def test_performance_filter_nonexistent_task_type():
    """Filtering by a task_type with no arms returns empty dict."""
    selector = ThompsonSamplingSelector()
    await selector.update("s1", "code", reward=1.0)

    stats = await selector.performance(task_type="nonexistent")
    assert stats == {}


async def test_performance_unfiltered_returns_all():
    """performance with no filter returns all arms across task types."""
    selector = ThompsonSamplingSelector()

    await selector.update("a", "code", reward=1.0)
    await selector.update("b", "review", reward=0.0)

    stats = await selector.performance()
    assert len(stats) == 2
    assert "a:code" in stats
    assert "b:review" in stats


# -- New arms / uniform prior -----------------------------------------------


async def test_new_arm_has_uniform_prior():
    """A newly created arm starts with alpha=1, beta=1 (uniform prior)."""
    selector = ThompsonSamplingSelector()

    # Trigger arm creation via select
    await selector.select("code", candidates=["new_strategy"])

    stats = await selector.performance()
    s = stats["new_strategy:code"]
    assert s.alpha == 1.0
    assert s.beta == 1.0
    assert s.total_trials == 0
    assert s.successes == 0
    assert s.avg_reward == 0.0
