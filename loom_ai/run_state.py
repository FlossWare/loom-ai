"""Agent run lifecycle state machine (#821).

Defines a single authoritative state machine for engineering
runs. All surfaces (DemoAgent, MCP, CLI, API) must report
the same semantic phase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Self


class RunPhase(str, Enum):
    """Lifecycle phase of an engineering run."""

    CREATED = "created"
    FETCHING = "fetching"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    VERIFYING = "verifying"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"


_TRANSITIONS: dict[RunPhase, set[RunPhase]] = {
    RunPhase.CREATED: {
        RunPhase.FETCHING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.FETCHING: {
        RunPhase.PLANNING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.PLANNING: {
        RunPhase.EXECUTING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.EXECUTING: {
        # DemoAgent currently performs the review loop inside its
        # execution phase. Keep the explicit REVIEWING state for
        # callers that expose review as a separate phase, while also
        # allowing the embedded-review execution path to proceed.
        RunPhase.REVIEWING,
        RunPhase.VERIFYING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.REVIEWING: {
        RunPhase.EXECUTING,
        RunPhase.VERIFYING,
        RunPhase.NEEDS_REVIEW,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.VERIFYING: {
        RunPhase.PERSISTING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.PERSISTING: {
        RunPhase.COMPLETED,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.COMPLETED: {
        RunPhase.PUBLISHED,
        RunPhase.FAILED,
    },
    RunPhase.NEEDS_REVIEW: {
        RunPhase.CANCELLED,
        RunPhase.FAILED,
    },
    RunPhase.PUBLISHED: set(),
    RunPhase.FAILED: set(),
    RunPhase.CANCELLED: set(),
}

_TERMINAL_STATES = {
    RunPhase.COMPLETED,
    RunPhase.FAILED,
    RunPhase.CANCELLED,
    RunPhase.PUBLISHED,
}


class IllegalTransitionError(Exception):
    """Raised on an invalid state transition."""

    def __init__(
        self,
        run_id: str,
        current: RunPhase,
        target: RunPhase,
    ) -> None:
        self.run_id = run_id
        self.current = current
        self.target = target
        super().__init__(
            f"Run {run_id}: illegal transition "
            f"{current.value} -> {target.value}"
        )


class RunStateMachine:
    """Tracks and enforces the lifecycle of a run."""

    def __init__(self, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self._run_id = run_id
        self._phase = RunPhase.CREATED
        self._history: list[tuple[str, RunPhase, RunPhase]] = []

    @property
    def phase(self) -> RunPhase:
        return self._phase

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_terminal(self) -> bool:
        return self._phase in _TERMINAL_STATES

    @property
    def history(self) -> list[tuple[str, RunPhase, RunPhase]]:
        return list(self._history)

    def can_transition(self, target: RunPhase) -> bool:
        return target in _TRANSITIONS.get(self._phase, set())

    def transition(self, target: RunPhase) -> None:
        if not self.can_transition(target):
            raise IllegalTransitionError(self._run_id, self._phase, target)
        old = self._phase
        self._phase = target
        ts = datetime.now(timezone.utc).isoformat()
        self._history.append((ts, old, target))

    def fail(self, error: str = "") -> None:
        if self.is_terminal:
            return
        self.transition(RunPhase.FAILED)

    def cancel(self) -> None:
        if self.is_terminal:
            return
        self.transition(RunPhase.CANCELLED)

    def to_dict(self) -> dict:
        return {
            "run_id": self._run_id,
            "phase": self._phase.value,
            "is_terminal": self.is_terminal,
            "history": [
                {"ts": ts, "from": old.value, "to": new.value}
                for ts, old, new in self._history
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        sm = cls(d["run_id"])
        phase = RunPhase(d["phase"])
        history = [
            (
                e["ts"],
                RunPhase(e["from"]),
                RunPhase(e["to"]),
            )
            for e in d.get("history", [])
        ]
        # Reject corrupt serialized state instead of silently restoring
        # a lifecycle that could permit an unsafe operation.
        current = RunPhase.CREATED
        for _, old, new in history:
            if old != current or new not in _TRANSITIONS.get(current, set()):
                raise ValueError("Invalid run state history")
            current = new
        if history and current != phase:
            raise ValueError("Run state phase does not match history")
        if not history and phase != RunPhase.CREATED:
            raise ValueError("Non-created state requires transition history")
        sm._phase = phase
        sm._history = history
        return sm
