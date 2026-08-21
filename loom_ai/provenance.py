"""Durable provenance and evidence ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Self
from uuid import uuid4


class EventKind(str, Enum):
    """All trackable event types in a run."""

    TASK_RECEIVED = "task_received"
    MODEL_CALL = "model_call"
    TOOL_INVOCATION = "tool_invocation"
    DECISION = "decision"
    ARTIFACT_CHANGED = "artifact_changed"
    VERIFICATION_RUN = "verification_run"
    VERIFICATION_SKIPPED = "verification_skipped"
    PERSISTENCE_WRITE = "persistence_write"
    PERSISTENCE_MEMORY_ONLY = "persistence_memory_only"
    GIT_OPERATION = "git_operation"
    PUBLICATION = "publication"
    SECRET_ACCESS = "secret_access"
    ERROR = "error"
    RECOVERY = "recovery"


@dataclass
class ProvenanceEvent:
    """A single provenance record."""

    event_id: str
    run_id: str
    kind: EventKind
    timestamp: str
    payload: dict[str, Any]
    verified: bool = False
    claim_source: str = "model"


RedactFn = Callable[[dict[str, Any]], dict[str, Any]]


def _redact_keys(
    sensitive: frozenset[str],
    placeholder: str = "***REDACTED***",
) -> RedactFn:
    """Return a redaction function for given keys."""

    def _redact(payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if k in sensitive:
                out[k] = placeholder
            elif isinstance(v, dict):
                out[k] = _redact(v)
            else:
                out[k] = v
        return out

    return _redact


class EvidenceLedger:
    """Append-only provenance ledger for a single run."""

    def __init__(
        self,
        run_id: str,
        redact: RedactFn | None = None,
    ) -> None:
        self._run_id = run_id
        self._redact = redact
        self._events: list[ProvenanceEvent] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    def record(
        self,
        kind: EventKind,
        payload: dict[str, Any],
        *,
        verified: bool = False,
        claim_source: str = "model",
    ) -> ProvenanceEvent:
        safe = self._redact(payload) if self._redact else dict(payload)
        event = ProvenanceEvent(
            event_id=str(uuid4()),
            run_id=self._run_id,
            kind=kind,
            timestamp=datetime.now(
                timezone.utc,
            ).isoformat(),
            payload=safe,
            verified=verified,
            claim_source=claim_source,
        )
        self._events.append(event)
        return event

    def mark_verified(
        self,
        event_id: str,
        verifier: str,
    ) -> None:
        for event in self._events:
            if event.event_id == event_id:
                event.verified = True
                event.claim_source = verifier
                return
        raise ValueError(f"Event {event_id} not found")

    @property
    def events(self) -> list[ProvenanceEvent]:
        return list(self._events)

    def evidence_chain(self) -> dict[str, Any]:
        return {
            "run_id": self._run_id,
            "event_count": len(self._events),
            "events": [
                {
                    "event_id": e.event_id,
                    "run_id": e.run_id,
                    "kind": e.kind.value,
                    "timestamp": e.timestamp,
                    "payload": e.payload,
                    "verified": e.verified,
                    "claim_source": e.claim_source,
                }
                for e in self._events
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.evidence_chain(),
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, data: str) -> Self:
        parsed = json.loads(data)
        ledger = cls(parsed["run_id"])
        for ed in parsed["events"]:
            event = ProvenanceEvent(
                event_id=ed["event_id"],
                run_id=ed["run_id"],
                kind=EventKind(ed["kind"]),
                timestamp=ed["timestamp"],
                payload=ed["payload"],
                verified=ed["verified"],
                claim_source=ed["claim_source"],
            )
            ledger._events.append(event)
        return ledger

    def unverified_claims(
        self,
    ) -> list[ProvenanceEvent]:
        return [e for e in self._events if e.claim_source == "model" and not e.verified]

    def persistence_audit(self) -> dict[str, Any]:
        unverified: list[str] = []
        memory_only: list[str] = []
        for e in self._events:
            if e.kind == EventKind.PERSISTENCE_WRITE and not e.verified:
                unverified.append(e.event_id)
            elif e.kind == EventKind.PERSISTENCE_MEMORY_ONLY:
                memory_only.append(e.event_id)
        return {
            "unverified_writes": unverified,
            "memory_only_writes": memory_only,
        }
