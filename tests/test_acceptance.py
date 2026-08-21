"""Tests for end-to-end acceptance harness."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from loom_ai.acceptance import (
    AcceptanceHarness,
    AcceptanceStep,
)
from loom_ai.provenance import EventKind, EvidenceLedger
from loom_ai.quality import QualificationSummary


def test_run_step_records_passing_result() -> None:
    harness = AcceptanceHarness("test_workspace")
    result = harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"key": "value"},
    )
    assert result.passed
    assert result.evidence == {"key": "value"}
    assert result.error == ""
    assert result.duration_ms >= 0


def test_run_step_records_failing_result() -> None:
    harness = AcceptanceHarness("test_workspace")

    def _fail() -> dict:
        msg = "boom"
        raise RuntimeError(msg)

    result = harness.run_step(
        AcceptanceStep.PREFLIGHT,
        _fail,
    )
    assert not result.passed
    assert result.evidence == {}
    assert "boom" in result.error
    assert result.duration_ms >= 0


def test_run_step_captures_duration() -> None:
    harness = AcceptanceHarness("test_workspace")

    def _slow() -> dict:
        time.sleep(0.05)
        return {}

    result = harness.run_step(
        AcceptanceStep.PREFLIGHT,
        _slow,
    )
    assert result.duration_ms >= 30


@patch("loom_ai.acceptance.PreflightChecker")
def test_run_preflight_uses_checker(
    mock_cls: MagicMock,
) -> None:
    mock_inst = mock_cls.return_value
    mock_inst.run_all.return_value = []
    mock_inst.summary.return_value = {
        "ready": True,
        "checks": [],
    }
    harness = AcceptanceHarness("test_workspace")
    result = harness.run_preflight()
    mock_cls.assert_called_once_with()
    mock_inst.run_all.assert_called_once()
    assert result.passed


@patch("loom_ai.acceptance.PreflightChecker")
def test_run_preflight_fails_when_not_ready(
    mock_cls: MagicMock,
) -> None:
    mock_inst = mock_cls.return_value
    mock_inst.run_all.return_value = []
    mock_inst.summary.return_value = {
        "ready": False,
        "checks": [
            {
                "dependency": "git",
                "status": "fail",
                "required": True,
                "message": "not found",
                "version": "",
            },
        ],
    }
    harness = AcceptanceHarness("test_workspace")
    result = harness.run_preflight()
    assert not result.passed
    assert "git" in result.error


def test_all_passed_true_when_all_pass() -> None:
    harness = AcceptanceHarness("test_workspace")
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"ok": True},
    )
    assert harness.all_passed()


def test_all_passed_false_when_any_fail() -> None:
    harness = AcceptanceHarness("test_workspace")
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: (_ for _ in ()).throw(  # type: ignore[func-returns-value]
            RuntimeError("fail"),
        ),
    )
    assert not harness.all_passed()


def test_report_returns_machine_readable_dict() -> None:
    harness = AcceptanceHarness("test_workspace")
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"key": "value"},
    )
    report = harness.report()
    assert "results" in report
    assert report["all_passed"] is True
    assert report["results"][0]["step"] == "preflight"


def test_to_qualification_returns_summary() -> None:
    harness = AcceptanceHarness("test_workspace")
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"ok": True},
    )
    summary = harness.to_qualification(
        commit_sha="abc123",
    )
    assert isinstance(summary, QualificationSummary)
    assert len(summary.gates) == 1
    assert summary.gates[0].passed


def test_ledger_records_step_events() -> None:
    ledger = EvidenceLedger(run_id="test")
    harness = AcceptanceHarness(
        "test_workspace",
        ledger=ledger,
    )
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"key": "value"},
    )
    events = ledger.events
    assert len(events) == 1
    assert events[0].kind == EventKind.VERIFICATION_RUN
    assert events[0].payload["step"] == "preflight"


def test_acceptance_step_has_all_values() -> None:
    assert len(AcceptanceStep) == 9
    assert AcceptanceStep.PREFLIGHT.value == "preflight"
    assert AcceptanceStep.PROVENANCE_CHECK.value == "provenance_check"


def test_results_ordered_by_execution() -> None:
    harness = AcceptanceHarness("test_workspace")
    harness.run_step(
        AcceptanceStep.PREFLIGHT,
        lambda: {"v": 1},
    )
    harness.run_step(
        AcceptanceStep.TASK_SUBMIT,
        lambda: {"v": 2},
    )
    results = harness.results
    assert results[0].step == AcceptanceStep.PREFLIGHT
    assert results[1].step == AcceptanceStep.TASK_SUBMIT
