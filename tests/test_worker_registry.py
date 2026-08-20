"""Tests for InMemoryWorkerRegistry: register/deregister, health check,
and model diversity with balanced and skewed distributions.
"""

import pytest

from loom_ai.backends.registry import InMemoryWorkerRegistry
from loom_ai.models_session import WorkerInfo


def _worker(
    wid: str,
    models: list[str] | None = None,
) -> WorkerInfo:
    """Shorthand factory for test workers."""
    return WorkerInfo(
        id=wid,
        name=f"worker-{wid}",
        endpoint=f"http://{wid}:5000",
        models=models or [],
    )


# ── register / deregister ──────────────────────────────────────────────


async def test_register_single_worker():
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1"))
    status = await reg.health_check()
    assert "w1" in status


async def test_register_multiple_workers():
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1"))
    await reg.register(_worker("w2"))
    await reg.register(_worker("w3"))
    status = await reg.health_check()
    assert set(status.keys()) == {"w1", "w2", "w3"}


async def test_register_overwrites_existing():
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1", models=["alpha"]))
    await reg.register(_worker("w1", models=["beta"]))
    report = await reg.model_diversity()
    # Only "beta" should remain -- the second register replaced the first.
    assert report.model_distribution == {"beta": 1}


async def test_deregister_removes_worker():
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1"))
    await reg.deregister("w1")
    status = await reg.health_check()
    assert "w1" not in status


async def test_deregister_nonexistent_is_silent():
    reg = InMemoryWorkerRegistry()
    await reg.deregister("ghost")  # should not raise


# ── health check ───────────────────────────────────────────────────────


async def test_health_check_returns_healthy_by_default():
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1"))
    status = await reg.health_check()
    ws = status["w1"]
    assert ws.worker_id == "w1"
    assert ws.healthy is True
    assert ws.last_check  # non-empty timestamp
    assert ws.latency_ms == 0.0
    assert ws.error is None


async def test_health_check_empty_registry():
    reg = InMemoryWorkerRegistry()
    status = await reg.health_check()
    assert status == {}


# ── model diversity ────────────────────────────────────────────────────


async def test_diversity_empty_registry():
    reg = InMemoryWorkerRegistry()
    report = await reg.model_diversity()
    assert report.model_distribution == {}
    assert report.dominant_model is None
    assert report.dominance_ratio == 0.0
    assert report.is_healthy is True


async def test_diversity_balanced_distribution():
    """Three workers each offering one distinct model -- perfectly balanced."""
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1", models=["opus"]))
    await reg.register(_worker("w2", models=["sonnet"]))
    await reg.register(_worker("w3", models=["haiku"]))
    report = await reg.model_diversity()

    assert report.model_distribution == {"opus": 1, "sonnet": 1, "haiku": 1}
    assert report.dominance_ratio == pytest.approx(1 / 3, abs=1e-9)
    assert report.is_healthy is True


async def test_diversity_skewed_distribution():
    """One model dominates 75% -- should be flagged unhealthy."""
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1", models=["opus"]))
    await reg.register(_worker("w2", models=["opus"]))
    await reg.register(_worker("w3", models=["opus"]))
    await reg.register(_worker("w4", models=["sonnet"]))
    report = await reg.model_diversity()

    assert report.dominant_model == "opus"
    assert report.dominance_ratio == pytest.approx(0.75)
    assert report.is_healthy is False


async def test_diversity_exactly_at_threshold():
    """70% dominance sits right on the boundary -- should be healthy."""
    reg = InMemoryWorkerRegistry()
    # 7 out of 10 model slots = 0.7
    for i in range(7):
        await reg.register(_worker(f"a{i}", models=["dominant"]))
    for i in range(3):
        await reg.register(_worker(f"b{i}", models=["minority"]))
    report = await reg.model_diversity()

    assert report.dominance_ratio == pytest.approx(0.7)
    assert report.is_healthy is True


async def test_diversity_workers_with_no_models():
    """Workers with empty model lists produce an empty distribution."""
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1", models=[]))
    await reg.register(_worker("w2", models=[]))
    report = await reg.model_diversity()
    assert report.model_distribution == {}
    assert report.is_healthy is True


async def test_diversity_multi_model_workers():
    """Workers advertising multiple models contribute to all counts."""
    reg = InMemoryWorkerRegistry()
    await reg.register(_worker("w1", models=["opus", "sonnet"]))
    await reg.register(_worker("w2", models=["sonnet", "haiku"]))
    report = await reg.model_diversity()

    assert report.model_distribution == {"opus": 1, "sonnet": 2, "haiku": 1}
    assert report.dominant_model == "sonnet"
    assert report.dominance_ratio == pytest.approx(2 / 4)
    assert report.is_healthy is True
