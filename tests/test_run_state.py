"""Tests for the agent run state machine (#821)."""

from __future__ import annotations

import pytest

from loom_ai.run_state import (
    IllegalTransitionError,
    RunPhase,
    RunStateMachine,
)


class TestRunPhase:
    def test_all_phases_are_strings(self):
        for phase in RunPhase:
            assert isinstance(phase.value, str)

    def test_terminal_states(self):
        from loom_ai.run_state import _TERMINAL_STATES

        assert RunPhase.COMPLETED in _TERMINAL_STATES
        assert RunPhase.FAILED in _TERMINAL_STATES
        assert RunPhase.CANCELLED in _TERMINAL_STATES
        assert RunPhase.PUBLISHED in _TERMINAL_STATES
        assert RunPhase.CREATED not in _TERMINAL_STATES


class TestRunStateMachine:
    def test_initial_state_is_created(self):
        sm = RunStateMachine("test-1")
        assert sm.phase == RunPhase.CREATED
        assert not sm.is_terminal

    def test_happy_path(self):
        sm = RunStateMachine("test-2")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.REVIEWING)
        sm.transition(RunPhase.VERIFYING)
        sm.transition(RunPhase.PERSISTING)
        sm.transition(RunPhase.COMPLETED)
        assert sm.phase == RunPhase.COMPLETED
        assert sm.is_terminal
        assert len(sm.history) == 7

    def test_publish_after_complete(self):
        sm = RunStateMachine("test-3")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.REVIEWING)
        sm.transition(RunPhase.VERIFYING)
        sm.transition(RunPhase.PERSISTING)
        sm.transition(RunPhase.COMPLETED)
        sm.transition(RunPhase.PUBLISHED)
        assert sm.phase == RunPhase.PUBLISHED
        assert sm.is_terminal

    def test_retry_loop(self):
        sm = RunStateMachine("test-retry")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.REVIEWING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.REVIEWING)
        sm.transition(RunPhase.VERIFYING)
        assert sm.phase == RunPhase.VERIFYING

    def test_illegal_transition_raises(self):
        sm = RunStateMachine("test-bad")
        with pytest.raises(IllegalTransitionError) as exc:
            sm.transition(RunPhase.COMPLETED)
        assert exc.value.run_id == "test-bad"
        assert exc.value.current == RunPhase.CREATED
        assert exc.value.target == RunPhase.COMPLETED

    def test_terminal_cannot_transition(self):
        sm = RunStateMachine("test-term")
        sm.transition(RunPhase.FETCHING)
        sm.fail()
        assert sm.phase == RunPhase.FAILED
        with pytest.raises(IllegalTransitionError):
            sm.transition(RunPhase.PLANNING)

    def test_fail_from_any_non_terminal(self):
        for phase in RunPhase:
            sm = RunStateMachine(f"fail-{phase.value}")
            sm._phase = phase
            if phase in (
                RunPhase.COMPLETED,
                RunPhase.FAILED,
                RunPhase.CANCELLED,
                RunPhase.PUBLISHED,
            ):
                sm.fail()
                assert sm.phase == phase
            else:
                sm.fail()
                assert sm.phase == RunPhase.FAILED

    def test_cancel_from_any_non_terminal(self):
        for phase in RunPhase:
            sm = RunStateMachine(
                f"cancel-{phase.value}"
            )
            sm._phase = phase
            if phase in (
                RunPhase.COMPLETED,
                RunPhase.FAILED,
                RunPhase.CANCELLED,
                RunPhase.PUBLISHED,
            ):
                sm.cancel()
                assert sm.phase == phase
            else:
                sm.cancel()
                assert sm.phase == RunPhase.CANCELLED

    def test_can_transition(self):
        sm = RunStateMachine("test-can")
        assert sm.can_transition(RunPhase.FETCHING)
        assert not sm.can_transition(
            RunPhase.COMPLETED
        )

    def test_to_dict_roundtrip(self):
        sm = RunStateMachine("test-rt")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        d = sm.to_dict()
        assert d["run_id"] == "test-rt"
        assert d["phase"] == "executing"
        assert not d["is_terminal"]
        assert len(d["history"]) == 3

        restored = RunStateMachine.from_dict(d)
        assert restored.run_id == "test-rt"
        assert restored.phase == RunPhase.EXECUTING
        assert len(restored.history) == 3

    def test_from_dict_preserves_history(self):
        sm = RunStateMachine("test-hist")
        sm.transition(RunPhase.FETCHING)
        sm.fail()
        d = sm.to_dict()
        restored = RunStateMachine.from_dict(d)
        assert restored.is_terminal
        assert restored.phase == RunPhase.FAILED
        assert len(restored.history) == 2
        _, _, target = restored.history[-1]
        assert target == RunPhase.FAILED

    def test_history_records_timestamps(self):
        sm = RunStateMachine("test-ts")
        sm.transition(RunPhase.FETCHING)
        ts, from_phase, to_phase = sm.history[0]
        assert "T" in ts
        assert from_phase == RunPhase.CREATED
        assert to_phase == RunPhase.FETCHING

    def test_needs_review_is_terminal_like(self):
        sm = RunStateMachine("test-nr")
        sm.transition(RunPhase.FETCHING)
        sm.transition(RunPhase.PLANNING)
        sm.transition(RunPhase.EXECUTING)
        sm.transition(RunPhase.REVIEWING)
        sm.transition(RunPhase.NEEDS_REVIEW)
        assert not sm.is_terminal
        assert sm.can_transition(RunPhase.CANCELLED)
        assert sm.can_transition(RunPhase.FAILED)
        assert not sm.can_transition(
            RunPhase.EXECUTING
        )

    def test_published_is_truly_terminal(self):
        sm = RunStateMachine("test-pub")
        sm._phase = RunPhase.PUBLISHED
        assert sm.is_terminal
        assert not sm.can_transition(RunPhase.FAILED)
        assert not sm.can_transition(
            RunPhase.COMPLETED
        )

    def test_run_id_property(self):
        sm = RunStateMachine("my-run")
        assert sm.run_id == "my-run"
