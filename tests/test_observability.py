"""Tests for loom_ai.backends.observability.InMemoryObservability."""

import pytest

from loom_ai.backends.observability import InMemoryObservability
from loom_ai.contracts_phase2 import ObservabilityBackend

# -- protocol conformance ------------------------------------------------


def test_satisfies_protocol():
    """InMemoryObservability must be recognised as an ObservabilityBackend."""
    assert isinstance(InMemoryObservability(), ObservabilityBackend)


# -- record_metric -------------------------------------------------------


async def test_record_metric_basic():
    obs = InMemoryObservability()
    await obs.record_metric("latency_ms", 42.5)
    metrics = obs.get_metrics()
    assert len(metrics) == 1
    assert metrics[0]["name"] == "latency_ms"
    assert metrics[0]["value"] == 42.5
    assert metrics[0]["labels"] == {}
    assert isinstance(metrics[0]["timestamp"], float)


async def test_record_metric_with_labels():
    obs = InMemoryObservability()
    await obs.record_metric("tokens", 150.0, labels={"model": "gpt-4o"})
    m = obs.get_metrics()[0]
    assert m["labels"] == {"model": "gpt-4o"}


async def test_record_multiple_metrics():
    obs = InMemoryObservability()
    await obs.record_metric("a", 1.0)
    await obs.record_metric("b", 2.0)
    await obs.record_metric("a", 3.0)
    assert len(obs.get_metrics()) == 3
    assert len(obs.get_metrics("a")) == 2
    assert len(obs.get_metrics("b")) == 1


# -- log_event -----------------------------------------------------------


async def test_log_event_defaults():
    obs = InMemoryObservability()
    await obs.log_event("server started")
    events = obs.get_events()
    assert len(events) == 1
    assert events[0]["event"] == "server started"
    assert events[0]["level"] == "info"
    assert events[0]["context"] == {}
    assert isinstance(events[0]["timestamp"], float)


async def test_log_event_custom_level_and_context():
    obs = InMemoryObservability()
    await obs.log_event("disk full", level="error", context={"disk": "/dev/sda1"})
    e = obs.get_events()[0]
    assert e["level"] == "error"
    assert e["context"] == {"disk": "/dev/sda1"}


async def test_get_events_filters_by_level():
    obs = InMemoryObservability()
    await obs.log_event("info event")
    await obs.log_event("warn event", level="warning")
    await obs.log_event("another info")
    assert len(obs.get_events("info")) == 2
    assert len(obs.get_events("warning")) == 1
    assert len(obs.get_events("debug")) == 0


# -- span lifecycle ------------------------------------------------------


async def test_start_and_end_span():
    obs = InMemoryObservability()
    span_id = await obs.start_span("process_request")
    assert isinstance(span_id, str)
    assert len(span_id) > 0

    span = obs.get_span(span_id)
    assert span is not None
    assert span["name"] == "process_request"
    assert span["parent"] is None
    assert span["start_time"] is not None
    assert span["end_time"] is None
    assert span["status"] is None

    await obs.end_span(span_id)
    span = obs.get_span(span_id)
    assert span["end_time"] is not None
    assert span["status"] == "ok"
    assert span["end_time"] >= span["start_time"]


async def test_end_span_with_error_status():
    obs = InMemoryObservability()
    span_id = await obs.start_span("failing_op")
    await obs.end_span(span_id, status="error")
    assert obs.get_span(span_id)["status"] == "error"


async def test_end_unknown_span_raises():
    obs = InMemoryObservability()
    with pytest.raises(KeyError, match="Unknown span id"):
        await obs.end_span("nonexistent-id")


# -- parent spans --------------------------------------------------------


async def test_parent_span():
    obs = InMemoryObservability()
    parent_id = await obs.start_span("parent_op")
    child_id = await obs.start_span("child_op", parent=parent_id)

    parent = obs.get_span(parent_id)
    child = obs.get_span(child_id)

    assert parent["parent"] is None
    assert child["parent"] == parent_id
    assert child["name"] == "child_op"


async def test_nested_spans():
    obs = InMemoryObservability()
    root = await obs.start_span("root")
    mid = await obs.start_span("mid", parent=root)
    leaf = await obs.start_span("leaf", parent=mid)

    assert obs.get_span(root)["parent"] is None
    assert obs.get_span(mid)["parent"] == root
    assert obs.get_span(leaf)["parent"] == mid


# -- get_span helper -----------------------------------------------------


async def test_get_span_returns_none_for_missing():
    obs = InMemoryObservability()
    assert obs.get_span("does-not-exist") is None


# -- unique span ids -----------------------------------------------------


async def test_span_ids_are_unique():
    obs = InMemoryObservability()
    ids = set()
    for i in range(50):
        sid = await obs.start_span(f"span-{i}")
        ids.add(sid)
    assert len(ids) == 50
