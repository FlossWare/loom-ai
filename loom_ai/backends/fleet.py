"""Distributed worker fleet dispatch for loom-ai.

Provides in-memory implementations for dispatching tasks across a pool
of workers, managing worker health, and balancing load.  Designed for
testing and single-process use -- production deployments would swap in
network-aware implementations via structural subtyping.

Classes
-------
FleetDispatcher -- dispatch tasks to workers by availability and capability
WorkerPool -- manage workers with periodic health-check snapshots
LoadBalancer -- pluggable routing: round-robin, least-connections,
               or capability-based
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from loom_ai.models_session import WorkerInfo, WorkerStatus

# ── data models ──────────────────────────────────────────────────────────


class RoutingStrategy(Enum):
    """Load-balancing strategy selector."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    CAPABILITY = "capability"


@dataclass
class DispatchResult:
    """Outcome of dispatching a task to a worker."""

    worker_id: str
    task: str
    accepted: bool
    reason: str = ""
    dispatched_at: str = ""


# ── WorkerPool ───────────────────────────────────────────────────────────


class WorkerPool:
    """Manage a pool of workers with health-check snapshots.

    Workers are stored by ``id``.  Health status is tracked separately
    so that callers can distinguish between registration and liveness.
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerInfo] = {}
        self._health: dict[str, WorkerStatus] = {}
        self._connections: dict[str, int] = {}

    # ── mutations ─────────────────────────────────────────────────────

    async def add(self, worker: WorkerInfo) -> None:
        """Register a worker and mark it healthy."""
        self._workers[worker.id] = worker
        self._health[worker.id] = WorkerStatus(
            worker_id=worker.id,
            healthy=True,
            last_check=datetime.now(timezone.utc).isoformat(),
            latency_ms=0.0,
        )
        self._connections.setdefault(worker.id, 0)

    async def remove(self, worker_id: str) -> None:
        """Remove a worker from the pool.  Silent if missing."""
        self._workers.pop(worker_id, None)
        self._health.pop(worker_id, None)
        self._connections.pop(worker_id, None)

    async def mark_unhealthy(self, worker_id: str, error: str = "") -> None:
        """Flag a worker as unhealthy."""
        if worker_id in self._health:
            self._health[worker_id] = WorkerStatus(
                worker_id=worker_id,
                healthy=False,
                last_check=datetime.now(timezone.utc).isoformat(),
                latency_ms=0.0,
                error=error or "health check failed",
            )

    async def mark_healthy(self, worker_id: str) -> None:
        """Flag a worker as healthy."""
        if worker_id in self._health:
            self._health[worker_id] = WorkerStatus(
                worker_id=worker_id,
                healthy=True,
                last_check=datetime.now(timezone.utc).isoformat(),
                latency_ms=0.0,
            )

    # ── queries ───────────────────────────────────────────────────────

    def all_workers(self) -> list[WorkerInfo]:
        """Return all registered workers (healthy or not)."""
        return list(self._workers.values())

    def healthy_workers(self) -> list[WorkerInfo]:
        """Return only workers whose latest health check passed."""
        return [
            w
            for w in self._workers.values()
            if self._health.get(w.id, WorkerStatus(w.id, False, "", 0.0)).healthy
        ]

    async def health_snapshot(self) -> dict[str, WorkerStatus]:
        """Return the current health status of every worker."""
        return dict(self._health)

    def connection_count(self, worker_id: str) -> int:
        """Return current connection count for a worker."""
        return self._connections.get(worker_id, 0)

    def increment_connections(self, worker_id: str) -> None:
        """Record that a new task was dispatched to *worker_id*."""
        self._connections[worker_id] = self._connections.get(worker_id, 0) + 1

    def decrement_connections(self, worker_id: str) -> None:
        """Record that a task on *worker_id* completed."""
        current = self._connections.get(worker_id, 0)
        self._connections[worker_id] = max(0, current - 1)


# ── LoadBalancer ─────────────────────────────────────────────────────────


class LoadBalancer:
    """Select workers using pluggable routing strategies.

    Supported strategies:

    * **round_robin** -- cycle through healthy workers in order.
    * **least_connections** -- pick the worker with fewest active tasks.
    * **capability** -- pick a healthy worker that advertises the
      requested capability.
    """

    def __init__(
        self,
        pool: WorkerPool,
        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
    ) -> None:
        self._pool = pool
        self._strategy = strategy
        self._rr_cycle: itertools.cycle[WorkerInfo] | None = None
        self._rr_worker_ids: list[str] = []

    @property
    def strategy(self) -> RoutingStrategy:
        """The active routing strategy."""
        return self._strategy

    def _rebuild_cycle(self, workers: list[WorkerInfo]) -> None:
        """Rebuild the round-robin cycle when the worker set changes."""
        ids = [w.id for w in workers]
        if ids != self._rr_worker_ids:
            self._rr_worker_ids = ids
            self._rr_cycle = itertools.cycle(workers) if workers else None

    def select(self, *, capability: str | None = None) -> WorkerInfo | None:
        """Pick the next worker according to the active strategy.

        Returns ``None`` when no suitable worker is available.
        """
        if self._strategy == RoutingStrategy.ROUND_ROBIN:
            return self._select_round_robin()
        if self._strategy == RoutingStrategy.LEAST_CONNECTIONS:
            return self._select_least_connections()
        if self._strategy == RoutingStrategy.CAPABILITY:
            return self._select_by_capability(capability)
        return None  # pragma: no cover

    # ── private selectors ─────────────────────────────────────────────

    def _select_round_robin(self) -> WorkerInfo | None:
        healthy = self._pool.healthy_workers()
        if not healthy:
            return None
        self._rebuild_cycle(healthy)
        if self._rr_cycle is None:
            return None
        return next(self._rr_cycle)

    def _select_least_connections(self) -> WorkerInfo | None:
        healthy = self._pool.healthy_workers()
        if not healthy:
            return None
        return min(healthy, key=lambda w: self._pool.connection_count(w.id))

    def _select_by_capability(self, capability: str | None) -> WorkerInfo | None:
        healthy = self._pool.healthy_workers()
        if capability is None:
            return healthy[0] if healthy else None
        for w in healthy:
            if capability in w.capabilities:
                return w
        return None


# ── FleetDispatcher ──────────────────────────────────────────────────────


class FleetDispatcher:
    """Dispatch tasks to workers based on availability and capabilities.

    Wraps a :class:`WorkerPool` and :class:`LoadBalancer` to provide a
    simple ``dispatch`` interface.
    """

    def __init__(
        self,
        pool: WorkerPool,
        balancer: LoadBalancer,
    ) -> None:
        self._pool = pool
        self._balancer = balancer

    async def dispatch(
        self,
        task: str,
        *,
        capability: str | None = None,
    ) -> DispatchResult:
        """Dispatch *task* to the best available worker.

        When *capability* is provided the load balancer will prefer
        workers that advertise it (only effective with the
        ``CAPABILITY`` strategy; other strategies ignore the hint).

        Returns a :class:`DispatchResult` indicating acceptance or
        rejection.
        """
        now = datetime.now(timezone.utc).isoformat()
        worker = self._balancer.select(capability=capability)
        if worker is None:
            return DispatchResult(
                worker_id="",
                task=task,
                accepted=False,
                reason="no suitable worker available",
                dispatched_at=now,
            )
        self._pool.increment_connections(worker.id)
        return DispatchResult(
            worker_id=worker.id,
            task=task,
            accepted=True,
            dispatched_at=now,
        )

    async def complete(self, worker_id: str) -> None:
        """Mark a previously dispatched task as complete."""
        self._pool.decrement_connections(worker_id)

    async def available_workers(self) -> list[WorkerInfo]:
        """Return all healthy workers in the pool."""
        return self._pool.healthy_workers()
