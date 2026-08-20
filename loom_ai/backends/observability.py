"""In-memory observability backend for loom-ai.

Provides metrics recording, structured event logging, and distributed
tracing spans -- all held in plain lists and dicts.  Zero external
dependencies; suitable for testing and local development.

Classes
-------
InMemoryObservability  -- list/dict-backed metrics, events, and spans
"""

from __future__ import annotations

import time
import uuid


class InMemoryObservability:
    """In-memory observability backend.

    Satisfies :class:`~loom_ai.contracts_workflow.ObservabilityBackend` via
    structural subtyping -- no inheritance required.

    All data is lost on process exit.
    """

    def __init__(self) -> None:
        self._metrics: list[dict] = []
        self._events: list[dict] = []
        self._spans: dict[str, dict] = {}

    # -- ObservabilityBackend protocol ------------------------------------

    async def record_metric(
        self, name: str, value: float, *, labels: dict | None = None
    ) -> None:
        """Record a numeric metric data point."""
        self._metrics.append(
            {
                "name": name,
                "value": value,
                "labels": labels or {},
                "timestamp": time.time(),
            }
        )

    async def log_event(
        self,
        event: str,
        *,
        level: str = "info",
        context: dict | None = None,
    ) -> None:
        """Emit a structured log event."""
        self._events.append(
            {
                "event": event,
                "level": level,
                "context": context or {},
                "timestamp": time.time(),
            }
        )

    async def start_span(self, name: str, *, parent: str | None = None) -> str:
        """Begin a tracing span and return its span id."""
        span_id = uuid.uuid4().hex
        self._spans[span_id] = {
            "span_id": span_id,
            "name": name,
            "parent": parent,
            "start_time": time.time(),
            "end_time": None,
            "status": None,
        }
        return span_id

    async def end_span(self, span_id: str, *, status: str = "ok") -> None:
        """Close a tracing span."""
        if span_id not in self._spans:
            raise KeyError(f"Unknown span id: {span_id}")
        self._spans[span_id]["end_time"] = time.time()
        self._spans[span_id]["status"] = status

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
