"""In-memory worker registry for loom-ai.

Provides a dict-backed implementation of the
:class:`~loom_ai.contracts_phase3.WorkerRegistry` protocol.  All data
is ephemeral -- nothing survives process exit.  No external dependencies.

Classes
-------
InMemoryWorkerRegistry -- dict-backed worker tracking with diversity analysis
"""

from __future__ import annotations

from datetime import datetime, timezone

from loom_ai.models_phase3 import DiversityReport, WorkerInfo, WorkerStatus


class InMemoryWorkerRegistry:
    """Dict-backed worker registry with health and diversity analysis.

    Satisfies :class:`~loom_ai.contracts_phase3.WorkerRegistry` via
    structural subtyping -- no inheritance required.

    Workers are stored by their ``id`` field.  Health checks default to
    healthy with the current UTC timestamp.  Diversity analysis counts
    model usage across all registered workers and flags the distribution
    as unhealthy when a single model exceeds 70% dominance.
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerInfo] = {}

    async def register(self, worker: WorkerInfo) -> None:
        """Add or update a worker in the registry."""
        self._workers[worker.id] = worker

    async def deregister(self, worker_id: str) -> None:
        """Remove a worker from the registry.

        Silently succeeds if the worker does not exist.
        """
        self._workers.pop(worker_id, None)

    async def health_check(self) -> dict[str, WorkerStatus]:
        """Return a healthy ``WorkerStatus`` for every registered worker.

        Each status snapshot uses the current UTC timestamp and zero
        latency.  A production implementation would ping each endpoint.
        """
        now = datetime.now(timezone.utc).isoformat()
        return {
            wid: WorkerStatus(
                worker_id=wid,
                healthy=True,
                last_check=now,
                latency_ms=0.0,
            )
            for wid in self._workers
        }

    async def model_diversity(self) -> DiversityReport:
        """Analyze model distribution across registered workers.

        Counts every model listed in each worker's ``models`` field.
        The dominant model is the one with the highest count, and the
        dominance ratio is ``count / total``.  The distribution is
        flagged unhealthy when the ratio exceeds 0.7.
        """
        counts: dict[str, int] = {}
        for worker in self._workers.values():
            for model in worker.models:
                counts[model] = counts.get(model, 0) + 1

        if not counts:
            return DiversityReport()

        total = sum(counts.values())
        dominant_model = max(counts, key=lambda m: counts[m])
        dominance_ratio = counts[dominant_model] / total
        return DiversityReport(
            model_distribution=counts,
            dominant_model=dominant_model,
            dominance_ratio=dominance_ratio,
            is_healthy=dominance_ratio <= 0.7,
        )
