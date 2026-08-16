"""Thompson Sampling strategy selector backend for loom-ai.

Uses a Beta-Bernoulli bandit per (strategy, task_type) pair to balance
exploration and exploitation when routing tasks to strategies.  All data
is held in memory -- no external dependencies required.

Classes
-------
ThompsonSamplingSelector -- in-memory Thompson Sampling bandit selector
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from loom_ai.models_phase2 import StrategyStats


@dataclass
class _BanditArm:
    """Internal mutable state for one (strategy, task_type) bandit arm."""

    alpha: float = 1.0
    beta: float = 1.0
    total_trials: int = 0
    successes: int = 0
    total_reward: float = 0.0


class ThompsonSamplingSelector:
    """In-memory Thompson Sampling strategy selector.

    Satisfies :class:`~loom_ai.contracts_phase2.StrategySelector` via
    structural subtyping.  Each (strategy, task_type) pair maintains
    independent Beta distribution parameters.  New arms start with a
    uniform prior (alpha=1, beta=1).
    """

    def __init__(self) -> None:
        # (strategy, task_type) -> arm state
        self._arms: dict[tuple[str, str], _BanditArm] = {}

    def _get_arm(self, strategy: str, task_type: str) -> _BanditArm:
        """Return the arm for *(strategy, task_type)*, creating if needed."""
        key = (strategy, task_type)
        if key not in self._arms:
            self._arms[key] = _BanditArm()
        return self._arms[key]

    async def select(self, task_type: str, *, candidates: list[str]) -> str:
        """Choose the best strategy for *task_type* from *candidates*.

        For each candidate, sample from its Beta(alpha, beta) distribution
        and return the candidate with the highest sample.
        """
        if not candidates:
            raise ValueError("candidates must not be empty")

        best_strategy = candidates[0]
        best_sample = -1.0

        for strategy in candidates:
            arm = self._get_arm(strategy, task_type)
            sample = random.betavariate(arm.alpha, arm.beta)
            if sample > best_sample:
                best_sample = sample
                best_strategy = strategy

        return best_strategy

    async def update(self, strategy: str, task_type: str, *, reward: float) -> None:
        """Record a reward observation for a strategy/task-type pair.

        Rewards above 0.5 increment alpha (success); rewards at or below
        0.5 increment beta (failure).  Running totals for trials,
        successes, and average reward are also maintained.
        """
        arm = self._get_arm(strategy, task_type)
        arm.total_trials += 1
        arm.total_reward += reward

        if reward > 0.5:
            arm.alpha += 1.0
            arm.successes += 1
        else:
            arm.beta += 1.0

    async def performance(
        self, *, task_type: str | None = None
    ) -> dict[str, StrategyStats]:
        """Return performance statistics for all known arms.

        When *task_type* is provided, only arms matching that task type are
        included.  The returned dict is keyed by ``"strategy:task_type"``.
        """
        result: dict[str, StrategyStats] = {}

        for (strategy, tt), arm in self._arms.items():
            if task_type is not None and tt != task_type:
                continue

            avg_reward = (
                arm.total_reward / arm.total_trials if arm.total_trials > 0 else 0.0
            )
            key = f"{strategy}:{tt}"
            result[key] = StrategyStats(
                strategy=strategy,
                task_type=tt,
                total_trials=arm.total_trials,
                successes=arm.successes,
                avg_reward=avg_reward,
                alpha=arm.alpha,
                beta=arm.beta,
            )

        return result
