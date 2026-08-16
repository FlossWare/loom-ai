"""Execution telemetry, cost tracking, and model feedback for loom-ai.

Provides three in-memory backends:

* :class:`ExecutionTelemetry` -- per-call latency, token counts, and costs
* :class:`CostTracker` -- aggregate cost accounting by model and provider
* :class:`ModelFeedback` -- quality rating history per model

When the ``prometheus_client`` package is available, an optional
:class:`PrometheusExporter` exposes Counters, Histograms, and Gauges
that mirror the in-memory data.  The import is guarded so the module
works without it installed.

All data is held in memory and lost on process exit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# -- Optional Prometheus import -----------------------------------------

try:
    from prometheus_client import Counter, Gauge, Histogram

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


# -- Data models --------------------------------------------------------


@dataclass
class ExecutionRecord:
    """A single LLM call execution record."""

    model: str
    provider: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    timestamp: float = field(default_factory=time.time)
    task_id: str = ""
    success: bool = True
    error: str = ""


@dataclass
class FeedbackRecord:
    """A quality rating for a model's output."""

    model: str
    rating: float  # 0.0 -- 1.0
    task_type: str = ""
    comment: str = ""
    timestamp: float = field(default_factory=time.time)


# -- ExecutionTelemetry -------------------------------------------------


class ExecutionTelemetry:
    """In-memory execution telemetry backend.

    Tracks per-call latency, token counts, and costs.  Provides query
    helpers for filtering and aggregation.
    """

    def __init__(self) -> None:
        self._records: list[ExecutionRecord] = []

    async def record(
        self,
        *,
        model: str,
        provider: str,
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost: float,
        task_id: str = "",
        success: bool = True,
        error: str = "",
    ) -> ExecutionRecord:
        """Record an LLM call and return the stored record."""
        rec = ExecutionRecord(
            model=model,
            provider=provider,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            task_id=task_id,
            success=success,
            error=error,
        )
        self._records.append(rec)
        return rec

    def get_records(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        task_id: str | None = None,
    ) -> list[ExecutionRecord]:
        """Return records, optionally filtered by model/provider/task_id."""
        out = self._records
        if model is not None:
            out = [r for r in out if r.model == model]
        if provider is not None:
            out = [r for r in out if r.provider == provider]
        if task_id is not None:
            out = [r for r in out if r.task_id == task_id]
        return list(out)

    def average_latency(self, *, model: str | None = None) -> float:
        """Return average latency in ms across matching records."""
        recs = self.get_records(model=model)
        if not recs:
            return 0.0
        return sum(r.latency_ms for r in recs) / len(recs)

    def total_tokens_used(self, *, model: str | None = None) -> int:
        """Return total tokens consumed across matching records."""
        recs = self.get_records(model=model)
        return sum(r.total_tokens for r in recs)

    def total_cost(self, *, model: str | None = None) -> float:
        """Return total cost across matching records."""
        recs = self.get_records(model=model)
        return sum(r.cost for r in recs)

    def success_rate(self, *, model: str | None = None) -> float:
        """Return the fraction of successful calls (0.0--1.0)."""
        recs = self.get_records(model=model)
        if not recs:
            return 0.0
        return sum(1 for r in recs if r.success) / len(recs)


# -- CostTracker --------------------------------------------------------


class CostTracker:
    """Aggregate cost accounting by model and provider.

    Wraps :class:`ExecutionTelemetry` records to produce rolled-up
    cost views.
    """

    def __init__(self) -> None:
        self._by_model: dict[str, float] = {}
        self._by_provider: dict[str, float] = {}
        self._total: float = 0.0

    async def add(self, *, model: str, provider: str, cost: float) -> None:
        """Record a cost entry."""
        self._by_model[model] = self._by_model.get(model, 0.0) + cost
        self._by_provider[provider] = self._by_provider.get(provider, 0.0) + cost
        self._total += cost

    @property
    def total(self) -> float:
        """Return total accumulated cost."""
        return self._total

    def by_model(self) -> dict[str, float]:
        """Return cost breakdown keyed by model."""
        return dict(self._by_model)

    def by_provider(self) -> dict[str, float]:
        """Return cost breakdown keyed by provider."""
        return dict(self._by_provider)

    def top_models(self, n: int = 5) -> list[tuple[str, float]]:
        """Return the *n* most expensive models as (model, cost) pairs."""
        items = sorted(self._by_model.items(), key=lambda kv: kv[1], reverse=True)
        return items[:n]

    def reset(self) -> None:
        """Reset all cost accumulators."""
        self._by_model.clear()
        self._by_provider.clear()
        self._total = 0.0


# -- ModelFeedback ------------------------------------------------------


class ModelFeedback:
    """Quality rating history per model.

    Records user/system feedback on model output quality and exposes
    per-model aggregate statistics.
    """

    def __init__(self) -> None:
        self._feedback: list[FeedbackRecord] = []

    async def rate(
        self,
        model: str,
        rating: float,
        *,
        task_type: str = "",
        comment: str = "",
    ) -> FeedbackRecord:
        """Record a quality rating (0.0--1.0) for *model*."""
        if not 0.0 <= rating <= 1.0:
            raise ValueError(f"rating must be in [0.0, 1.0], got {rating}")
        rec = FeedbackRecord(
            model=model,
            rating=rating,
            task_type=task_type,
            comment=comment,
        )
        self._feedback.append(rec)
        return rec

    def get_feedback(
        self,
        *,
        model: str | None = None,
        task_type: str | None = None,
    ) -> list[FeedbackRecord]:
        """Return feedback records, optionally filtered."""
        out = self._feedback
        if model is not None:
            out = [f for f in out if f.model == model]
        if task_type is not None:
            out = [f for f in out if f.task_type == task_type]
        return list(out)

    def average_rating(self, *, model: str | None = None) -> float:
        """Return the mean rating for *model* (or all models)."""
        recs = self.get_feedback(model=model)
        if not recs:
            return 0.0
        return sum(r.rating for r in recs) / len(recs)

    def model_rankings(self) -> list[tuple[str, float]]:
        """Return models ranked by average rating (descending)."""
        models: dict[str, list[float]] = {}
        for f in self._feedback:
            models.setdefault(f.model, []).append(f.rating)
        ranked = [(m, sum(rs) / len(rs)) for m, rs in models.items()]
        ranked.sort(key=lambda kv: kv[1], reverse=True)
        return ranked


# -- Prometheus exporter (optional) -------------------------------------


class PrometheusExporter:
    """Expose telemetry data as Prometheus metrics.

    Requires ``prometheus_client``.  If the library is not installed,
    instantiation raises :class:`ImportError`.
    """

    def __init__(self, *, prefix: str = "loom") -> None:
        if not _HAS_PROMETHEUS:
            raise ImportError("prometheus_client is required for PrometheusExporter")

        self.call_count = Counter(
            f"{prefix}_llm_calls_total",
            "Total LLM calls",
            ["model", "provider"],
        )
        self.token_count = Counter(
            f"{prefix}_tokens_total",
            "Total tokens consumed",
            ["model", "direction"],
        )
        self.latency = Histogram(
            f"{prefix}_call_latency_ms",
            "Call latency in milliseconds",
            ["model"],
        )
        self.cost_total = Counter(
            f"{prefix}_cost_total",
            "Total cost in dollars",
            ["model", "provider"],
        )
        self.error_count = Counter(
            f"{prefix}_errors_total",
            "Total failed calls",
            ["model"],
        )
        self.avg_rating = Gauge(
            f"{prefix}_model_avg_rating",
            "Average quality rating",
            ["model"],
        )

    def observe_execution(self, record: ExecutionRecord) -> None:
        """Push an execution record into Prometheus metrics."""
        self.call_count.labels(model=record.model, provider=record.provider).inc()
        self.token_count.labels(model=record.model, direction="prompt").inc(
            record.prompt_tokens
        )
        self.token_count.labels(model=record.model, direction="completion").inc(
            record.completion_tokens
        )
        self.latency.labels(model=record.model).observe(record.latency_ms)
        self.cost_total.labels(model=record.model, provider=record.provider).inc(
            record.cost
        )
        if not record.success:
            self.error_count.labels(model=record.model).inc()

    def observe_feedback(self, feedback: FeedbackRecord, avg: float) -> None:
        """Update the average-rating gauge for a model."""
        self.avg_rating.labels(model=feedback.model).set(avg)
