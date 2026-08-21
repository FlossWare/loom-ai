"""Tests for provenance and evidence ledger."""

from __future__ import annotations

from uuid import UUID

import pytest

from loom_ai.provenance import (
    EventKind,
    EvidenceLedger,
    _redact_keys,
)


def _make_redactor():
    return _redact_keys(
        frozenset({"password", "api_key", "token"}),
    )


def test_record_creates_event_with_correct_fields():
    ledger = EvidenceLedger(run_id="run-1")
    event = ledger.record(
        EventKind.TASK_RECEIVED,
        {"task": "fix bug"},
    )
    assert isinstance(UUID(event.event_id), UUID)
    assert event.run_id == "run-1"
    assert event.kind == EventKind.TASK_RECEIVED
    assert event.payload == {"task": "fix bug"}
    assert event.verified is False
    assert event.claim_source == "model"


def test_record_redacts_secrets_from_payload():
    redact = _make_redactor()
    ledger = EvidenceLedger(
        run_id="run-1",
        redact=redact,
    )
    event = ledger.record(
        EventKind.SECRET_ACCESS,
        {"password": "hunter2", "safe": "ok"},
    )
    assert event.payload["password"] == "***REDACTED***"
    assert event.payload["safe"] == "ok"


def test_mark_verified_updates_event():
    ledger = EvidenceLedger(run_id="run-1")
    event = ledger.record(
        EventKind.MODEL_CALL,
        {"prompt": "hello"},
    )
    ledger.mark_verified(event.event_id, "pytest")
    assert ledger.events[0].verified is True
    assert ledger.events[0].claim_source == "pytest"


def test_mark_verified_unknown_raises():
    ledger = EvidenceLedger(run_id="run-1")
    with pytest.raises(ValueError, match="not found"):
        ledger.mark_verified("bad-id", "pytest")


def test_evidence_chain_returns_full_summary():
    ledger = EvidenceLedger(run_id="run-1")
    ledger.record(
        EventKind.TASK_RECEIVED,
        {"task": "t"},
    )
    chain = ledger.evidence_chain()
    assert chain["run_id"] == "run-1"
    assert chain["event_count"] == 1
    assert chain["events"][0]["kind"] == "task_received"


def test_to_json_from_json_roundtrip():
    ledger = EvidenceLedger(run_id="run-1")
    ledger.record(
        EventKind.MODEL_CALL,
        {"model": "gpt-4o"},
    )
    ledger.record(
        EventKind.VERIFICATION_RUN,
        {"cmd": "pytest"},
        verified=True,
        claim_source="verifier",
    )
    data = ledger.to_json()
    restored = EvidenceLedger.from_json(data)
    assert len(restored.events) == 2
    assert restored.events[0].kind == EventKind.MODEL_CALL
    assert restored.events[1].verified is True
    assert restored.run_id == "run-1"


def test_unverified_claims_filters():
    ledger = EvidenceLedger(run_id="run-1")
    ledger.record(
        EventKind.MODEL_CALL,
        {"x": 1},
        verified=False,
    )
    ledger.record(
        EventKind.VERIFICATION_RUN,
        {"x": 2},
        verified=True,
        claim_source="verifier",
    )
    unv = ledger.unverified_claims()
    assert len(unv) == 1
    assert unv[0].payload == {"x": 1}


def test_persistence_audit_flags_memory_only():
    ledger = EvidenceLedger(run_id="run-1")
    ledger.record(
        EventKind.PERSISTENCE_MEMORY_ONLY,
        {"data": "cached"},
    )
    audit = ledger.persistence_audit()
    assert len(audit["memory_only_writes"]) == 1
    assert len(audit["unverified_writes"]) == 0


def test_persistence_audit_flags_unverified():
    ledger = EvidenceLedger(run_id="run-1")
    ledger.record(
        EventKind.PERSISTENCE_WRITE,
        {"target": "db"},
    )
    audit = ledger.persistence_audit()
    assert len(audit["unverified_writes"]) == 1


def test_verification_skipped_tracked():
    ledger = EvidenceLedger(run_id="run-1")
    e = ledger.record(
        EventKind.VERIFICATION_SKIPPED,
        {"reason": "unavailable"},
    )
    assert e.kind == EventKind.VERIFICATION_SKIPPED
    assert ledger.events[0].payload["reason"] == ("unavailable")


def test_secret_access_redacts_value():
    redact = _make_redactor()
    ledger = EvidenceLedger(
        run_id="run-1",
        redact=redact,
    )
    ledger.record(
        EventKind.SECRET_ACCESS,
        {"api_key": "sk-12345"},
    )
    assert ledger.events[0].payload["api_key"] == ("***REDACTED***")


def test_reconstruct_after_restart():
    original = EvidenceLedger(run_id="run-1")
    original.record(
        EventKind.TASK_RECEIVED,
        {"task": "original"},
    )
    data = original.to_json()

    restored = EvidenceLedger.from_json(data)
    restored.record(
        EventKind.MODEL_CALL,
        {"prompt": "new"},
    )
    assert len(restored.events) == 2
    assert restored.events[0].kind == EventKind.TASK_RECEIVED
    assert restored.events[1].kind == EventKind.MODEL_CALL


def test_multiple_runs_no_cross_contamination():
    r1 = EvidenceLedger(run_id="run-1")
    r2 = EvidenceLedger(run_id="run-2")
    r1.record(EventKind.TASK_RECEIVED, {"t": "a"})
    r2.record(EventKind.TASK_RECEIVED, {"t": "b"})
    assert r1.events[0].run_id == "run-1"
    assert r2.events[0].run_id == "run-2"
    assert len(r1.events) == 1
    assert len(r2.events) == 1


def test_all_event_kinds_defined():
    assert len(EventKind) == 14
