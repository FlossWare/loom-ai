from __future__ import annotations

import pytest

from loom_ai.acceptance import AcceptanceHarness, AcceptanceStep
from loom_ai.canary import CanaryGuard, CanaryPolicy, LimitExceeded
from loom_ai.quality import QualificationSummary
from loom_ai.run_state import IllegalTransitionError, RunPhase, RunStateMachine


def test_run_state_allows_embedded_review_execution_path() -> None:
    sm = RunStateMachine("run-1")
    sm.transition(RunPhase.FETCHING)
    sm.transition(RunPhase.PLANNING)
    sm.transition(RunPhase.EXECUTING)
    sm.transition(RunPhase.VERIFYING)
    sm.transition(RunPhase.PERSISTING)
    sm.transition(RunPhase.COMPLETED)
    assert sm.is_terminal


def test_run_state_rejects_invalid_serialized_history() -> None:
    with pytest.raises(ValueError):
        RunStateMachine.from_dict(
            {
                "run_id": "run-1",
                "phase": "completed",
                "history": [],
            }
        )


def test_acceptance_does_not_turn_false_verdict_into_pass() -> None:
    harness = AcceptanceHarness(".")
    result = harness.run_step(
        AcceptanceStep.VERIFICATION,
        lambda: {"passed": False, "error": "lint failed"},
    )
    assert not result.passed
    assert not harness.all_passed()


def test_empty_qualification_is_not_qualified() -> None:
    summary = QualificationSummary(
        timestamp="now",
        commit_sha="abc",
        python_version="3.12",
    )
    assert not summary.qualified


def test_canary_allowed_directory_accepts_descendants() -> None:
    guard = CanaryGuard(CanaryPolicy(allowed_paths=frozenset({"src"})))
    guard.start()
    guard.check_file_change("src/loom_ai/example.py")
    assert guard.summary()["files_changed"] == 1


def test_canary_requires_start() -> None:
    guard = CanaryGuard(CanaryPolicy())
    with pytest.raises(RuntimeError):
        guard.check_tool_call()


def test_canary_publication_is_denied_by_default() -> None:
    guard = CanaryGuard(CanaryPolicy())
    guard.start()
    with pytest.raises(LimitExceeded):
        guard.check_publication()


def test_state_machine_rejects_illegal_transition() -> None:
    sm = RunStateMachine("run-2")
    with pytest.raises(IllegalTransitionError):
        sm.transition(RunPhase.PUBLISHED)
