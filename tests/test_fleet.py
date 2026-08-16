"""Tests for fleet dispatch: WorkerPool, LoadBalancer, and FleetDispatcher."""

from loom_ai.backends.fleet import (
    FleetDispatcher,
    LoadBalancer,
    RoutingStrategy,
    WorkerPool,
)
from loom_ai.models_phase3 import WorkerInfo


def _worker(
    wid: str,
    capabilities: list[str] | None = None,
    models: list[str] | None = None,
) -> WorkerInfo:
    """Shorthand factory for test workers."""
    return WorkerInfo(
        id=wid,
        name=f"worker-{wid}",
        endpoint=f"http://{wid}:5000",
        capabilities=capabilities or [],
        models=models or [],
    )


# ── WorkerPool ────────────────────────────────────────────────────────────


async def test_pool_add_and_list():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    assert len(pool.all_workers()) == 2


async def test_pool_remove_worker():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.remove("w1")
    assert pool.all_workers() == []


async def test_pool_remove_missing_is_silent():
    pool = WorkerPool()
    await pool.remove("ghost")  # should not raise


async def test_pool_healthy_workers_excludes_unhealthy():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    await pool.mark_unhealthy("w1", error="timeout")
    healthy = pool.healthy_workers()
    assert len(healthy) == 1
    assert healthy[0].id == "w2"


async def test_pool_mark_healthy_restores():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.mark_unhealthy("w1")
    await pool.mark_healthy("w1")
    assert len(pool.healthy_workers()) == 1


async def test_pool_health_snapshot():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.mark_unhealthy("w1", error="disk full")
    snap = await pool.health_snapshot()
    assert snap["w1"].healthy is False
    assert snap["w1"].error == "disk full"


async def test_pool_connection_tracking():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    assert pool.connection_count("w1") == 0
    pool.increment_connections("w1")
    pool.increment_connections("w1")
    assert pool.connection_count("w1") == 2
    pool.decrement_connections("w1")
    assert pool.connection_count("w1") == 1


async def test_pool_decrement_below_zero():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    pool.decrement_connections("w1")
    assert pool.connection_count("w1") == 0


# ── LoadBalancer: round-robin ─────────────────────────────────────────────


async def test_round_robin_cycles():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    ids = [lb.select().id for _ in range(4)]
    assert ids == ["w1", "w2", "w1", "w2"]


async def test_round_robin_no_workers():
    pool = WorkerPool()
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    assert lb.select() is None


async def test_round_robin_skips_unhealthy():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    await pool.mark_unhealthy("w1")
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    assert lb.select().id == "w2"
    assert lb.select().id == "w2"


# ── LoadBalancer: least-connections ───────────────────────────────────────


async def test_least_connections_prefers_idle():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    pool.increment_connections("w1")
    pool.increment_connections("w1")
    lb = LoadBalancer(pool, RoutingStrategy.LEAST_CONNECTIONS)
    assert lb.select().id == "w2"


async def test_least_connections_no_workers():
    pool = WorkerPool()
    lb = LoadBalancer(pool, RoutingStrategy.LEAST_CONNECTIONS)
    assert lb.select() is None


# ── LoadBalancer: capability ──────────────────────────────────────────────


async def test_capability_routing_finds_match():
    pool = WorkerPool()
    await pool.add(_worker("w1", capabilities=["code"]))
    await pool.add(_worker("w2", capabilities=["review"]))
    lb = LoadBalancer(pool, RoutingStrategy.CAPABILITY)
    result = lb.select(capability="review")
    assert result is not None
    assert result.id == "w2"


async def test_capability_routing_no_match():
    pool = WorkerPool()
    await pool.add(_worker("w1", capabilities=["code"]))
    lb = LoadBalancer(pool, RoutingStrategy.CAPABILITY)
    assert lb.select(capability="review") is None


async def test_capability_routing_none_returns_first():
    pool = WorkerPool()
    await pool.add(_worker("w1", capabilities=["code"]))
    lb = LoadBalancer(pool, RoutingStrategy.CAPABILITY)
    result = lb.select(capability=None)
    assert result is not None
    assert result.id == "w1"


async def test_lb_strategy_property():
    pool = WorkerPool()
    lb = LoadBalancer(pool, RoutingStrategy.LEAST_CONNECTIONS)
    assert lb.strategy == RoutingStrategy.LEAST_CONNECTIONS


# ── FleetDispatcher ───────────────────────────────────────────────────────


async def test_dispatch_accepted():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    fd = FleetDispatcher(pool, lb)

    result = await fd.dispatch("summarize document")
    assert result.accepted is True
    assert result.worker_id == "w1"
    assert result.task == "summarize document"
    assert result.dispatched_at != ""


async def test_dispatch_rejected_no_workers():
    pool = WorkerPool()
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    fd = FleetDispatcher(pool, lb)

    result = await fd.dispatch("summarize document")
    assert result.accepted is False
    assert result.worker_id == ""
    assert "no suitable worker" in result.reason


async def test_dispatch_increments_connections():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    fd = FleetDispatcher(pool, lb)

    await fd.dispatch("task-1")
    assert pool.connection_count("w1") == 1
    await fd.dispatch("task-2")
    assert pool.connection_count("w1") == 2


async def test_dispatch_complete_decrements():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    fd = FleetDispatcher(pool, lb)

    await fd.dispatch("task-1")
    await fd.complete("w1")
    assert pool.connection_count("w1") == 0


async def test_dispatch_with_capability():
    pool = WorkerPool()
    await pool.add(_worker("w1", capabilities=["code"]))
    await pool.add(_worker("w2", capabilities=["review"]))
    lb = LoadBalancer(pool, RoutingStrategy.CAPABILITY)
    fd = FleetDispatcher(pool, lb)

    result = await fd.dispatch("review PR", capability="review")
    assert result.accepted is True
    assert result.worker_id == "w2"


async def test_available_workers():
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    await pool.mark_unhealthy("w2")
    lb = LoadBalancer(pool, RoutingStrategy.ROUND_ROBIN)
    fd = FleetDispatcher(pool, lb)

    available = await fd.available_workers()
    assert len(available) == 1
    assert available[0].id == "w1"


async def test_least_connections_dispatch_balances():
    """Multiple dispatches with least-connections should spread load."""
    pool = WorkerPool()
    await pool.add(_worker("w1"))
    await pool.add(_worker("w2"))
    lb = LoadBalancer(pool, RoutingStrategy.LEAST_CONNECTIONS)
    fd = FleetDispatcher(pool, lb)

    r1 = await fd.dispatch("task-1")
    r2 = await fd.dispatch("task-2")
    # First goes to either; second should go to the other
    assert {r1.worker_id, r2.worker_id} == {"w1", "w2"}
