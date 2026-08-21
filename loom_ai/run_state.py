"""Agent run state machine (#821).

Tracks the lifecycle of a dogfood agent run through ordered phases.
Illegal transitions raise IllegalTransitionError. Terminal phases
(COMPLETED, FAILED, CANCELLED, PUBLISHED) accept only self-transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RunPhase(str, Enum):
    """Lifecycle phases for a dogfood agent run."""

    CREATED = "created"
    FETCHING = "fetching"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PUBLISHED = "published"


_TERMINAL = frozenset(
    {
        RunPhase.COMPLETED,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
        RunPhase.PUBLISHED,
    }
)

_ALLOWED: dict[RunPhase, frozenset[RunPhase]] = {
    RunPhase.CREATED: frozenset({RunPhase.FETCHING, RunPhase.FAILED, RunPhase.CANCELLED}),
    RunPhase.FETCHING: frozenset(
        {RunPhase.PLANNING, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.PLANNING: frozenset(
        {RunPhase.EXECUTING, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.EXECUTING: frozenset(
        {RunPhase.VERIFYING, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.VERIFYING: frozenset(
        {RunPhase.PERSISTING, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.PERSISTING: frozenset(
        {RunPhase.COMPLETED, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.COMPLETED: frozenset({RunPhase.PUBLISHED, RunPhase.COMPLETED}),
    RunPhase.FAILED: frozenset({RunPhase.FAILED}),
    RunPhase.CANCELLED: frozenset({RunPhase.CANCELLED}),
    RunPhase.PUBLISHED: frozenset({RunPhase.PUBLISHED}),
}


class IllegalTransitionError(RuntimeError):
    """Raised when a phase transition is not allowed."""

    def __init__(self, from_phase: RunPhase, to_phase: RunPhase) -> None:
        self.from_phase = from_phase
        self.to_phase = to_phase
        super().__init__(f"Illegal transition: {from_phase.value} -> {to_phase.value}")


@dataclass
class TransitionRecord:
    ts: str
    from_phase: str
    to_phase: str


@dataclass
class RunStateMachine:
    """Finite state machine for a single agent run."""

    run_id: str
    _phase: RunPhase = field(default=RunPhase.CREATED, init=False, repr=False)
    _history: list[TransitionRecord] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")

    @property
    def phase(self) -> RunPhase:
        return self._phase

    @property
    def history(self) -> list[TransitionRecord]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._phase in _TERMINAL

    def can_transition(self, to: RunPhase) -> bool:
        return to in _ALLOWED.get(self._phase, frozenset())

    def transition(self, to: RunPhase) -> None:
        if not self.can_transition(to):
            raise IllegalTransitionError(self._phase, to)
        if to == self._phase:
            return
        rec = TransitionRecord(
            ts=datetime.now(timezone.utc).isoformat(),
            from_phase=self._phase.value,
            to_phase=to.value,
        )
        self._history.append(rec)
        self._phase = to

    def fail(self) -> None:
        if self._phase not in _TERMINAL:
            self.transition(RunPhase.FAILED)

    def cancel(self) -> None:
        if self._phase not in _TERMINAL:
            self.transition(RunPhase.CANCELLED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self._phase.value,
            "is_terminal": self.is_terminal,
            "history": [
                {"ts": h.ts, "from": h.from_phase, "to": h.to_phase}
                for h in self._history
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunStateMachine:
        run_id = d.get("run_id") or ""
        phase_s = d.get("phase", "created")
        history = d.get("history") or []
        if phase_s != "created" and not history:
            raise ValueError("non-created phase requires history")
        sm = cls(run_id=run_id)
        try:
            sm._phase = RunPhase(phase_s)
        except ValueError as exc:
            raise ValueError(f"unknown phase: {phase_s}") from exc
        for h in history:
            sm._history.append(
                TransitionRecord(
                    ts=h.get("ts", ""),
                    from_phase=h.get("from", h.get("from_phase", "")),
                    to_phase=h.get("to", h.get("to_phase", "")),
                )
            )
        return sm
