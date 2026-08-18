"""Structured logging observability backend for loom-ai.

Emits structured log events with trace-id correlation using Python's
stdlib :mod:`logging`.  Supports plain-text and JSON output formats.
Zero external dependencies; ``structlog`` can be used via the optional
``observability`` extra but is not required.

Classes
-------
StructuredLoggingObservability  -- stdlib-logging-backed metrics, events, and spans
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # NOSONAR — reserved for future protocol type imports


class _JsonFormatter(logging.Formatter):
    """Logging formatter that emits one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": record.created,
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
        }
        extra = getattr(record, "_structured_extra", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


class StructuredLoggingObservability:
    """Structured logging observability backend.

    Satisfies :class:`~loom_ai.contracts_phase2.ObservabilityBackend` via
    structural subtyping -- no inheritance required.

    Parameters
    ----------
    logger_name:
        Name passed to :func:`logging.getLogger`.
    json_format:
        When ``True``, attach a :class:`_JsonFormatter` to the logger's
        handlers (or add a new :class:`logging.StreamHandler` if none exist).
    trace_id:
        Optional trace id for correlating all events within a single
        execution.  When ``None``, a new random id is generated.
    """

    def __init__(
        self,
        *,
        logger_name: str = "loom_ai.observability",
        json_format: bool = False,
        trace_id: str | None = None,
    ) -> None:
        self._logger = logging.getLogger(logger_name)
        self._trace_id = trace_id or uuid.uuid4().hex
        self._spans: dict[str, dict] = {}
        self._metrics: list[dict] = []
        self._events: list[dict] = []

        if json_format:
            formatter = _JsonFormatter()
            if not self._logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)
            else:
                for handler in self._logger.handlers:
                    handler.setFormatter(formatter)

    @property
    def trace_id(self) -> str:
        """Return the trace id used for event correlation."""
        return self._trace_id

    # -- ObservabilityBackend protocol ------------------------------------

    async def record_metric(  # NOSONAR — async required by protocol
        self, name: str, value: float, *, labels: dict | None = None
    ) -> None:
        """Record a numeric metric data point."""
        entry = {
            "name": name,
            "value": value,
            "labels": labels or {},
            "timestamp": time.time(),
            "trace_id": self._trace_id,
        }
        self._metrics.append(entry)
        self._logger.info(
            "metric %s=%s",
            name,
            value,
            extra={"_structured_extra": entry},
        )

    async def log_event(  # NOSONAR — async required by ObservabilityBackend protocol
        self,
        event: str,
        *,
        level: str = "info",
        context: dict | None = None,
    ) -> None:
        """Emit a structured log event."""
        entry = {
            "event": event,
            "level": level,
            "context": context or {},
            "timestamp": time.time(),
            "trace_id": self._trace_id,
        }
        self._events.append(entry)
        log_level = getattr(logging, level.upper(), logging.INFO)
        self._logger.log(
            log_level,
            "%s",
            event,
            extra={"_structured_extra": entry},
        )

    async def start_span(  # NOSONAR — async required by ObservabilityBackend protocol
        self, name: str, *, parent: str | None = None
    ) -> str:
        """Begin a tracing span and return its span id."""
        span_id = uuid.uuid4().hex
        self._spans[span_id] = {
            "span_id": span_id,
            "name": name,
            "parent": parent,
            "start_time": time.time(),
            "end_time": None,
            "status": None,
            "trace_id": self._trace_id,
        }
        self._logger.debug(
            "span_start %s",
            name,
            extra={
                "_structured_extra": {
                    "span_id": span_id,
                    "parent": parent,
                    "trace_id": self._trace_id,
                }
            },
        )
        return span_id

    async def end_span(  # NOSONAR — async required by ObservabilityBackend protocol
        self, span_id: str, *, status: str = "ok"
    ) -> None:
        """Close a tracing span."""
        if span_id not in self._spans:
            raise KeyError(f"Unknown span id: {span_id}")
        self._spans[span_id]["end_time"] = time.time()
        self._spans[span_id]["status"] = status
        self._logger.debug(
            "span_end %s",
            self._spans[span_id]["name"],
            extra={
                "_structured_extra": {
                    "span_id": span_id,
                    "status": status,
                    "trace_id": self._trace_id,
                }
            },
        )

    # -- Query helpers (not part of the protocol) -------------------------

    def get_metrics(self, name: str | None = None) -> list[dict]:
        """Return recorded metrics, optionally filtered by *name*."""
        if name is None:
            return list(self._metrics)
        return [m for m in self._metrics if m["name"] == name]

    def get_events(self, level: str | None = None) -> list[dict]:
        """Return logged events, optionally filtered by *level*."""
        if level is None:
            return list(self._events)
        return [e for e in self._events if e["level"] == level]

    def get_span(self, span_id: str) -> dict | None:
        """Return a span by id, or ``None`` if not found."""
        return self._spans.get(span_id)
