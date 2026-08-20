"""In-memory budget tracker for loom-ai.

Tracks token usage and estimated cost against configurable budgets.
All data is held in plain dicts -- zero external dependencies.
Suitable for testing, local development, and the 'crush' deployment
profile.  All data is lost on process exit.

Classes
-------
InMemoryBudgetTracker -- dict-backed token/cost tracker with per-model rates
"""

from __future__ import annotations

from loom_ai.models_workflow import BudgetStatus, CostReport, TokenUsage

# Default cost per 1 000 tokens when no model-specific rate is configured.
_DEFAULT_RATE_PER_1K = 0.01


def _extract_provider(model: str) -> str:
    """Derive a provider name from a model identifier.

    Heuristic: if the model string contains ``/`` (e.g.
    ``"openai/gpt-4o"``), everything before the first slash is the
    provider.  Otherwise the full model name is used as the provider.
    """
    if "/" in model:
        return model.split("/", 1)[0]
    return model


class InMemoryBudgetTracker:
    """Fully async, dict-backed budget tracker.

    Satisfies :class:`~loom_ai.contracts_workflow.BudgetTracker` via
    structural subtyping.

    Parameters
    ----------
    model_rates:
        Optional mapping of model name to cost-per-1k-tokens.  Models
        not listed fall back to *default_rate*.
    default_rate:
        Cost charged per 1 000 tokens for unlisted models.
    """

    def __init__(
        self,
        *,
        model_rates: dict[str, float] | None = None,
        default_rate: float = _DEFAULT_RATE_PER_1K,
    ) -> None:
        self._model_rates: dict[str, float] = dict(model_rates or {})
        self._default_rate = default_rate

        # Budget limits (None == unlimited)
        self._max_tokens: int | None = None
        self._max_cost: float | None = None

        # Accumulated counters
        self._total_tokens: int = 0
        self._total_cost: float = 0.0

        # Breakdowns
        self._by_model: dict[str, float] = {}  # model -> cost
        self._by_provider: dict[str, float] = {}  # provider -> cost
        self._by_task: dict[str, float] = {}  # task_id -> cost

        self._tokens_by_model: dict[str, int] = {}  # model -> tokens

    # -- helpers ----------------------------------------------------------

    def _rate_for(self, model: str) -> float:
        """Return the per-1k-token rate for *model*."""
        return self._model_rates.get(model, self._default_rate)

    # -- protocol methods -------------------------------------------------

    async def record_usage(
        self, model: str, usage: TokenUsage, *, task_id: str | None = None
    ) -> None:
        """Record token consumption for a model invocation."""
        tokens = usage.total_tokens
        cost = tokens * self._rate_for(model) / 1000.0

        self._total_tokens += tokens
        self._total_cost += cost

        # Per-model
        self._by_model[model] = self._by_model.get(model, 0.0) + cost
        self._tokens_by_model[model] = self._tokens_by_model.get(model, 0) + tokens

        # Per-provider
        provider = _extract_provider(model)
        self._by_provider[provider] = self._by_provider.get(provider, 0.0) + cost

        # Per-task
        if task_id is not None:
            self._by_task[task_id] = self._by_task.get(task_id, 0.0) + cost

    async def remaining(self) -> BudgetStatus:
        """Return the current budget status."""
        tokens_remaining: int | None = None
        if self._max_tokens is not None:
            tokens_remaining = max(0, self._max_tokens - self._total_tokens)

        cost_remaining: float | None = None
        if self._max_cost is not None:
            cost_remaining = max(0.0, self._max_cost - self._total_cost)

        return BudgetStatus(
            tokens_used=self._total_tokens,
            tokens_remaining=tokens_remaining,
            cost_used=self._total_cost,
            cost_remaining=cost_remaining,
        )

    async def set_budget(
        self,
        *,
        max_tokens: int | None = None,
        max_cost: float | None = None,
    ) -> None:
        """Set or update budget limits."""
        if max_tokens is not None:
            self._max_tokens = max_tokens
        if max_cost is not None:
            self._max_cost = max_cost

    async def cost_report(self) -> CostReport:
        """Return an aggregated cost breakdown."""
        return CostReport(
            total_cost=self._total_cost,
            by_model=dict(self._by_model),
            by_provider=dict(self._by_provider),
            by_task=dict(self._by_task),
        )
