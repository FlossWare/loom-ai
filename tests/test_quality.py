"""Tests for quality gate definitions (#817)."""

from __future__ import annotations

from loom_ai.quality import (
    GateResult,
    QualificationSummary,
    QualityGate,
)


# 1. All 7 QualityGate values
def test_all_quality_gates():
    assert len(QualityGate) == 7
    expected = {
        "lint",
        "format",
        "tests",
        "coverage",
        "imports",
        "security_audit",
        "version_format",
    }
    actual = {g.value for g in QualityGate}
    assert actual == expected


# 2. GateResult passes/fails
def test_gate_result_passes():
    r = GateResult(QualityGate.LINT, True)
    assert r.passed
    assert r.detail == ""


def test_gate_result_fails():
    r = GateResult(
        QualityGate.TESTS,
        False,
        "3 failures",
    )
    assert not r.passed
    assert r.detail == "3 failures"


# 3. qualified = True when all pass
def test_qualified_all_pass():
    summary = QualificationSummary(
        timestamp="2026-08-21T00:00:00Z",
        commit_sha="abc123",
        python_version="3.12",
        gates=[
            GateResult(QualityGate.LINT, True),
            GateResult(QualityGate.TESTS, True),
            GateResult(QualityGate.COVERAGE, True),
        ],
    )
    assert summary.qualified


# 4. qualified = False when any fail
def test_qualified_one_fails():
    summary = QualificationSummary(
        timestamp="2026-08-21T00:00:00Z",
        commit_sha="abc123",
        python_version="3.12",
        gates=[
            GateResult(QualityGate.FORMAT, True),
            GateResult(
                QualityGate.COVERAGE,
                False,
                "58% < 60%",
            ),
        ],
    )
    assert not summary.qualified


# 5. to_dict/from_dict roundtrip
def test_roundtrip():
    original = QualificationSummary(
        timestamp="2026-08-21T01:00:00Z",
        commit_sha="def456",
        python_version="3.13",
        gates=[
            GateResult(QualityGate.LINT, True),
            GateResult(
                QualityGate.TESTS,
                False,
                "timeout",
                duration_ms=5000.0,
            ),
        ],
    )
    d = original.to_dict()
    assert d["qualified"] is False
    restored = QualificationSummary.from_dict(d)
    assert restored.timestamp == original.timestamp
    assert restored.commit_sha == original.commit_sha
    assert len(restored.gates) == 2
    assert restored.gates[1].detail == "timeout"
    assert restored.gates[1].duration_ms == 5000.0
    assert not restored.qualified


# 6. Empty gates = not qualified (fail-closed; no silent pass)
def test_empty_gates_not_qualified():
    summary = QualificationSummary(
        timestamp="2026-08-21T00:00:00Z",
        commit_sha="000000",
        python_version="3.10",
    )
    assert not summary.qualified
