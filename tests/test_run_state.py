"""Tests for the agent run state machine (#821)."""

from __future__ import annotations

import pytest

from loom_ai.run_state import IllegalTransitionError, RunPhase, RunStateMachine


class TestRunPhase:
    def test_all_phases_exist(self):
        expected = {
            "created",
            "fetching",
            "planning",
            "executing",
            "reviewing",
            "verifying",
            "persisting",
            "completed",
            "failed",
            "cancelled",
            "needs_review",
            "published",
        }
        assert {p.value for p in RunPhase} == expected


class TestTransitions:
    def test_happy_path(self):
        sm = RunStateMachine("run-1")
        assert sm.phase == RunPhase.CREATED
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.VERIFYING)
        sm.transition(RunPhase.PERSISTING)
        sm.transition(RunPhase.COMPLETED)
        assert sm.is_terminal
        assert sm.phase == RunPhase.COMPLETED

    def test_fail_from_any_active(self):
        for phase in (
            RunPhase.FETCHING,
            RunPhase.PLANNING,
            RunPhase.EXECUTING,
            RunPhase.VERIFYING,
            RunPhase.PERSISTING,
        ):
            sm = RunStateMachine(f"fail-{phase.value}")
            sm._phase = phase
            sm.fail()
            assert sm.phase == RunPhase.FAILED
            assert sm.is_terminal

    def test_cancel_from_any_active(self):
        for phase in RunPhase:
            if phase in (
                RunPhase.COMPLETED,
                RunPhase.FAILED,
                RunPhase.CANCELLED,
                RunPhase.PUBLISHED,
            ):
                continue
            sm = RunStateMachine(f"cancel-{phase.value}")
            sm._phase = phase
            sm.cancel()
            assert sm.phase == RunPhase.CANCELLED

    def test_illegal_transition_raises(self):
        sm = RunStateMachine("run-2")
        with pytest.raises(IllegalTransitionError):
            sm.transition(RunPhase.COMPLETED)

    def test_can_transition(self):
        sm = RunStateMachine("run-3")
        assert sm.can_transition(RunPhase.FETCHING)
        assert not sm.can_transition(RunPhase.COMPLETED)


class TestSerialization:
    def test_roundtrip(self):
        sm = RunStateMachine("run-4")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        d = sm.to_dict()
        restored = RunStateMachine.from_dict(d)
        assert restored.run_id == sm.run_id
        assert restored.phase == sm.phase
        assert len(restored.history) == len(sm.history)

    def test_empty_history_rejected_when_not_created(self):
        with pytest.raises(ValueError):
            RunStateMachine.from_dict(
                {"run_id": "x", "phase": "completed", "history": []}
            )


class TestPublished:
    def test_published_from_completed(self):
        sm = RunStateMachine("run-5")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.VERIFYING)
        sm.transition(RunPhase.PERSISTING)
        sm.transition(RunPhase.COMPLETED)
        sm.transition(RunPhase.PUBLISHED)
        assert sm.phase == RunPhase.PUBLISHED
        assert sm.is_terminal


class TestTerminalGuards:
    def test_no_transition_from_failed(self):
        sm = RunStateMachine("run-6")
        sm.fail()
        assert sm.can_transition(RunPhase.FAILED)
        assert not sm.can_transition(RunPhase.EXECUTING)

    def test_no_transition_from_cancelled(self):
        sm = RunStateMachine("run-7")
        sm.cancel()
        assert not sm.can_transition(RunPhase.FAILED)
        assert not sm.can_transition(RunPhase.COMPLETED)


class TestRunId:
    def test_run_id_preserved(self):
        sm = RunStateMachine("my-run")
        assert sm.run_id == "my-run"
