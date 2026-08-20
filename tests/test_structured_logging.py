"""Tests for loom_ai.backends.structured_logging.StructuredLoggingObservability."""

import json
import logging

import pytest

from loom_ai.backends.structured_logging import StructuredLoggingObservability
from loom_ai.contracts_workflow import ObservabilityBackend

# -- protocol conformance ------------------------------------------------


def test_satisfies_protocol():
    """StructuredLoggingObservability must be recognised as an ObservabilityBackend."""
    assert isinstance(StructuredLoggingObservability(), ObservabilityBackend)


# -- trace_id ------------------------------------------------------------


def test_default_trace_id():
    obs = StructuredLoggingObservability()
    assert isinstance(obs.trace_id, str)
    assert len(obs.trace_id) > 0


def test_custom_trace_id():
    obs = StructuredLoggingObservability(trace_id="custom-trace-123")
    assert obs.trace_id == "custom-trace-123"


def test_unique_default_trace_ids():
    ids = {StructuredLoggingObservability().trace_id for _ in range(20)}
    assert len(ids) == 20


# -- record_metric -------------------------------------------------------


async def test_record_metric_basic():
    obs = StructuredLoggingObservability()
    await obs.record_metric("latency_ms", 42.5)
    metrics = obs.get_metrics()
    assert len(metrics) == 1
    assert metrics[0]["name"] == "latency_ms"
    assert metrics[0]["value"] == 42.5
    assert metrics[0]["labels"] == {}
    assert isinstance(metrics[0]["timestamp"], float)
    assert metrics[0]["trace_id"] == obs.trace_id


async def test_record_metric_with_labels():
    obs = StructuredLoggingObservability()
    await obs.record_metric("tokens", 150.0, labels={"model": "gpt-4o"})
    m = obs.get_metrics()[0]
    assert m["labels"] == {"model": "gpt-4o"}


async def test_record_multiple_metrics():
    obs = StructuredLoggingObservability()
    await obs.record_metric("a", 1.0)
    await obs.record_metric("b", 2.0)
    await obs.record_metric("a", 3.0)
    assert len(obs.get_metrics()) == 3
    assert len(obs.get_metrics("a")) == 2
    assert len(obs.get_metrics("b")) == 1


# -- log_event -----------------------------------------------------------


async def test_log_event_defaults():
    obs = StructuredLoggingObservability()
    await obs.log_event("server started")
    events = obs.get_events()
    assert len(events) == 1
    assert events[0]["event"] == "server started"
    assert events[0]["level"] == "info"
    assert events[0]["context"] == {}
    assert isinstance(events[0]["timestamp"], float)
    assert events[0]["trace_id"] == obs.trace_id


async def test_log_event_custom_level_and_context():
    obs = StructuredLoggingObservability()
    await obs.log_event("disk full", level="error", context={"disk": "/dev/sda1"})
    e = obs.get_events()[0]
    assert e["level"] == "error"
    assert e["context"] == {"disk": "/dev/sda1"}


async def test_get_events_filters_by_level():
    obs = StructuredLoggingObservability()
    await obs.log_event("info event")
    await obs.log_event("warn event", level="warning")
    await obs.log_event("another info")
    assert len(obs.get_events("info")) == 2
    assert len(obs.get_events("warning")) == 1
    assert len(obs.get_events("debug")) == 0


# -- span lifecycle ------------------------------------------------------


async def test_start_and_end_span():
    obs = StructuredLoggingObservability()
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
    assert span["trace_id"] == obs.trace_id

    await obs.end_span(span_id)
    span = obs.get_span(span_id)
    assert span["end_time"] is not None
    assert span["status"] == "ok"
    assert span["end_time"] >= span["start_time"]


async def test_end_span_with_error_status():
    obs = StructuredLoggingObservability()
    span_id = await obs.start_span("failing_op")
    await obs.end_span(span_id, status="error")
    assert obs.get_span(span_id)["status"] == "error"


async def test_end_unknown_span_raises():
    obs = StructuredLoggingObservability()
    with pytest.raises(KeyError, match="Unknown span id"):
        await obs.end_span("nonexistent-id")


# -- parent spans --------------------------------------------------------


async def test_parent_span():
    obs = StructuredLoggingObservability()
    parent_id = await obs.start_span("parent_op")
    child_id = await obs.start_span("child_op", parent=parent_id)

    parent = obs.get_span(parent_id)
    child = obs.get_span(child_id)

    assert parent["parent"] is None
    assert child["parent"] == parent_id
    assert child["name"] == "child_op"


async def test_nested_spans():
    obs = StructuredLoggingObservability()
    root = await obs.start_span("root")
    mid = await obs.start_span("mid", parent=root)
    leaf = await obs.start_span("leaf", parent=mid)

    assert obs.get_span(root)["parent"] is None
    assert obs.get_span(mid)["parent"] == root
    assert obs.get_span(leaf)["parent"] == mid


# -- get_span helper -----------------------------------------------------


async def test_get_span_returns_none_for_missing():
    obs = StructuredLoggingObservability()
    assert obs.get_span("does-not-exist") is None


# -- unique span ids -----------------------------------------------------


async def test_span_ids_are_unique():
    obs = StructuredLoggingObservability()
    ids = set()
    for i in range(50):
        sid = await obs.start_span(f"span-{i}")
        ids.add(sid)
    assert len(ids) == 50


# -- trace_id correlation ------------------------------------------------


async def test_all_entries_share_trace_id():
    """Metrics, events, and spans from one instance share the same trace_id."""
    obs = StructuredLoggingObservability(trace_id="shared-trace")
    await obs.record_metric("m", 1.0)
    await obs.log_event("e")
    span_id = await obs.start_span("s")

    assert obs.get_metrics()[0]["trace_id"] == "shared-trace"
    assert obs.get_events()[0]["trace_id"] == "shared-trace"
    assert obs.get_span(span_id)["trace_id"] == "shared-trace"


# -- JSON format output --------------------------------------------------


async def test_json_format_output(caplog):
    """JSON formatter produces valid JSON log lines."""
    logger_name = "test_json_format"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    logger.addHandler(handler)

    obs = StructuredLoggingObservability(
        logger_name=logger_name,
        json_format=True,
        trace_id="json-trace",
    )

    await obs.log_event("test event", context={"key": "value"})

    for h in logger.handlers:
        fmt = h.formatter
        if fmt is not None:
            record = logging.LogRecord(
                name=logger_name,
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="formatted test",
                args=(),
                exc_info=None,
            )
            record._structured_extra = {"trace_id": "json-trace"}
            output = fmt.format(record)
            parsed = json.loads(output)
            assert parsed["message"] == "formatted test"
            assert parsed["trace_id"] == "json-trace"
            break

    logger.handlers.clear()


async def test_json_format_creates_handler_if_none():
    """JSON format adds a StreamHandler when the logger has no handlers."""
    logger_name = "test_json_no_handlers"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()

    obs = StructuredLoggingObservability(
        logger_name=logger_name,
        json_format=True,
    )
    _ = obs

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)

    logger.handlers.clear()


# -- stdlib logging integration ------------------------------------------


async def test_log_event_uses_correct_log_level():
    """Events logged at 'error' should use logging.ERROR."""
    logger_name = "test_log_levels"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    captured: list[logging.LogRecord] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    logger.addHandler(_CaptureHandler())

    obs = StructuredLoggingObservability(logger_name=logger_name)
    await obs.log_event("info msg")
    await obs.log_event("error msg", level="error")
    await obs.log_event("debug msg", level="debug")

    assert captured[0].levelno == logging.INFO
    assert captured[1].levelno == logging.ERROR
    assert captured[2].levelno == logging.DEBUG

    logger.handlers.clear()
