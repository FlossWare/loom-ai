"""Tests for loom_ai.backends.telemetry."""

import pytest

from loom_ai.backends.telemetry import (
    _HAS_PROMETHEUS,
    CostTracker,
    ExecutionRecord,
    ExecutionTelemetry,
    FeedbackRecord,
    ModelFeedback,
    PrometheusExporter,
)

# ── ExecutionTelemetry ──────────────────────────────────────────────────


async def test_record_stores_execution():
    tel = ExecutionTelemetry()
    rec = await tel.record(
        model="gpt-4o",
        provider="openai",
        latency_ms=150.0,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost=0.003,
    )
    assert isinstance(rec, ExecutionRecord)
    assert rec.model == "gpt-4o"
    assert rec.provider == "openai"
    assert rec.latency_ms == 150.0
    assert rec.total_tokens == 150
    assert rec.success is True


async def test_record_with_failure():
    tel = ExecutionTelemetry()
    rec = await tel.record(
        model="claude-3",
        provider="anthropic",
        latency_ms=500.0,
        prompt_tokens=200,
        completion_tokens=0,
        total_tokens=200,
        cost=0.001,
        success=False,
        error="rate limited",
    )
    assert rec.success is False
    assert rec.error == "rate limited"


async def test_get_records_unfiltered():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    await tel.record(
        model="b",
        provider="p",
        latency_ms=2,
        prompt_tokens=2,
        completion_tokens=2,
        total_tokens=4,
        cost=0.02,
    )
    assert len(tel.get_records()) == 2


async def test_get_records_filter_by_model():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    await tel.record(
        model="b",
        provider="p",
        latency_ms=2,
        prompt_tokens=2,
        completion_tokens=2,
        total_tokens=4,
        cost=0.02,
    )
    assert len(tel.get_records(model="a")) == 1
    assert tel.get_records(model="a")[0].model == "a"


async def test_get_records_filter_by_provider():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="openai",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    await tel.record(
        model="b",
        provider="anthropic",
        latency_ms=2,
        prompt_tokens=2,
        completion_tokens=2,
        total_tokens=4,
        cost=0.02,
    )
    recs = tel.get_records(provider="anthropic")
    assert len(recs) == 1
    assert recs[0].provider == "anthropic"


async def test_get_records_filter_by_task_id():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
        task_id="t1",
    )
    await tel.record(
        model="a",
        provider="p",
        latency_ms=2,
        prompt_tokens=2,
        completion_tokens=2,
        total_tokens=4,
        cost=0.02,
        task_id="t2",
    )
    assert len(tel.get_records(task_id="t1")) == 1


async def test_average_latency():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=100,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    await tel.record(
        model="a",
        provider="p",
        latency_ms=200,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    assert tel.average_latency() == 150.0


async def test_average_latency_empty():
    tel = ExecutionTelemetry()
    assert tel.average_latency() == 0.0


async def test_average_latency_filtered():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=100,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    await tel.record(
        model="b",
        provider="p",
        latency_ms=300,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
    )
    assert tel.average_latency(model="a") == 100.0
    assert tel.average_latency(model="b") == 300.0


async def test_total_tokens_used():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost=0.01,
    )
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
        cost=0.01,
    )
    assert tel.total_tokens_used() == 45


async def test_total_cost():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.005,
    )
    await tel.record(
        model="b",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.010,
    )
    assert abs(tel.total_cost() - 0.015) < 1e-9


async def test_success_rate():
    tel = ExecutionTelemetry()
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
        success=True,
    )
    await tel.record(
        model="a",
        provider="p",
        latency_ms=1,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost=0.01,
        success=False,
    )
    assert tel.success_rate() == 0.5


async def test_success_rate_empty():
    tel = ExecutionTelemetry()
    assert tel.success_rate() == 0.0


# ── CostTracker ────────────────────────────────────────────────────────


async def test_cost_tracker_add_and_total():
    ct = CostTracker()
    await ct.add(model="gpt-4o", provider="openai", cost=0.05)
    await ct.add(model="claude-3", provider="anthropic", cost=0.03)
    assert abs(ct.total - 0.08) < 1e-9


async def test_cost_tracker_by_model():
    ct = CostTracker()
    await ct.add(model="gpt-4o", provider="openai", cost=0.05)
    await ct.add(model="gpt-4o", provider="openai", cost=0.02)
    await ct.add(model="claude-3", provider="anthropic", cost=0.03)
    bm = ct.by_model()
    assert abs(bm["gpt-4o"] - 0.07) < 1e-9
    assert abs(bm["claude-3"] - 0.03) < 1e-9


async def test_cost_tracker_by_provider():
    ct = CostTracker()
    await ct.add(model="gpt-4o", provider="openai", cost=0.05)
    await ct.add(model="claude-3", provider="anthropic", cost=0.03)
    bp = ct.by_provider()
    assert abs(bp["openai"] - 0.05) < 1e-9
    assert abs(bp["anthropic"] - 0.03) < 1e-9


async def test_cost_tracker_top_models():
    ct = CostTracker()
    await ct.add(model="a", provider="p", cost=0.10)
    await ct.add(model="b", provider="p", cost=0.50)
    await ct.add(model="c", provider="p", cost=0.30)
    top = ct.top_models(n=2)
    assert len(top) == 2
    assert top[0][0] == "b"
    assert top[1][0] == "c"


async def test_cost_tracker_reset():
    ct = CostTracker()
    await ct.add(model="a", provider="p", cost=0.10)
    ct.reset()
    assert ct.total == 0.0
    assert ct.by_model() == {}
    assert ct.by_provider() == {}


# ── ModelFeedback ──────────────────────────────────────────────────────


async def test_feedback_rate_stores():
    fb = ModelFeedback()
    rec = await fb.rate("gpt-4o", 0.9, task_type="code", comment="great")
    assert isinstance(rec, FeedbackRecord)
    assert rec.model == "gpt-4o"
    assert rec.rating == 0.9
    assert rec.task_type == "code"
    assert rec.comment == "great"


async def test_feedback_rate_out_of_range():
    fb = ModelFeedback()
    with pytest.raises(ValueError, match="rating must be in"):
        await fb.rate("gpt-4o", 1.5)
    with pytest.raises(ValueError, match="rating must be in"):
        await fb.rate("gpt-4o", -0.1)


async def test_feedback_rate_boundary():
    fb = ModelFeedback()
    r0 = await fb.rate("a", 0.0)
    r1 = await fb.rate("a", 1.0)
    assert r0.rating == 0.0
    assert r1.rating == 1.0


async def test_feedback_get_unfiltered():
    fb = ModelFeedback()
    await fb.rate("a", 0.5)
    await fb.rate("b", 0.8)
    assert len(fb.get_feedback()) == 2


async def test_feedback_get_by_model():
    fb = ModelFeedback()
    await fb.rate("a", 0.5)
    await fb.rate("b", 0.8)
    assert len(fb.get_feedback(model="a")) == 1


async def test_feedback_get_by_task_type():
    fb = ModelFeedback()
    await fb.rate("a", 0.5, task_type="code")
    await fb.rate("a", 0.8, task_type="review")
    assert len(fb.get_feedback(task_type="code")) == 1


async def test_feedback_average_rating():
    fb = ModelFeedback()
    await fb.rate("a", 0.6)
    await fb.rate("a", 0.8)
    assert abs(fb.average_rating(model="a") - 0.7) < 1e-9


async def test_feedback_average_rating_empty():
    fb = ModelFeedback()
    assert fb.average_rating() == 0.0


async def test_feedback_model_rankings():
    fb = ModelFeedback()
    await fb.rate("a", 0.9)
    await fb.rate("b", 0.5)
    await fb.rate("c", 0.7)
    rankings = fb.model_rankings()
    assert rankings[0][0] == "a"
    assert rankings[1][0] == "c"
    assert rankings[2][0] == "b"


# ── PrometheusExporter ─────────────────────────────────────────────────


def test_prometheus_exporter_requires_library():
    """If prometheus_client is not installed, instantiation raises ImportError."""
    if _HAS_PROMETHEUS:
        pytest.skip("prometheus_client is installed")
    with pytest.raises(ImportError, match="prometheus_client"):
        PrometheusExporter()
