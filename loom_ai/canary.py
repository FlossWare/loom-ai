"""Canary mode and kill-switch for dogfood runs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CanaryPolicy:
    """Limits for a canary-mode run."""

    max_files_changed: int = 5
    max_file_size_bytes: int = 50_000
    max_tool_calls: int = 50
    max_subprocesses: int = 10
    max_duration_seconds: int = 300
    max_retries: int = 3
    max_concurrent_workers: int = 2
    max_pr_attempts: int = 1
    allowed_paths: frozenset[str] = frozenset()
    require_human_approval: bool = True
    allow_publication: bool = False

    def __post_init__(self) -> None:
        for name in (
            "max_files_changed",
            "max_file_size_bytes",
            "max_tool_calls",
            "max_subprocesses",
            "max_duration_seconds",
            "max_retries",
            "max_concurrent_workers",
            "max_pr_attempts",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


class LimitExceeded(RuntimeError):
    """A canary policy limit was exceeded."""

    def __init__(self, limit_name: str, value: Any, max_value: Any) -> None:
        self.limit_name = limit_name
        self.value = value
        self.max_value = max_value
        super().__init__(f"{limit_name} limit exceeded: {value} > {max_value}")


class KillSwitchActive(RuntimeError):
    """The kill-switch has been activated."""


class CanaryGuard:
    """Enforce canary policy limits during a run."""

    def __init__(self, policy: CanaryPolicy) -> None:
        self._policy = policy
        self._killed = False
        self._started = False
        self._tool_calls = 0
        self._subprocesses = 0
        self._files_changed: set[str] = set()
        self._pr_attempts = 0
        self._start_time: float | None = None
        self._events: list[dict[str, Any]] = []

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._start_time = time.monotonic()
        self._events.append({"type": "start"})

    def kill(self, reason: str = "") -> None:
        self._killed = True
        self._events.append({"type": "kill", "reason": reason})

    @property
    def is_killed(self) -> bool:
        return self._killed

    def _check_killed(self) -> None:
        if self._killed:
            raise KillSwitchActive()
        if not self._started:
            raise RuntimeError("CanaryGuard.start() must be called before checks")

    def check_tool_call(self) -> None:
        self._check_killed()
        self._tool_calls += 1
        if self._tool_calls > self._policy.max_tool_calls:
            raise LimitExceeded(
                "max_tool_calls", self._tool_calls, self._policy.max_tool_calls
            )

    def check_subprocess(self) -> None:
        self._check_killed()
        self._subprocesses += 1
        if self._subprocesses > self._policy.max_subprocesses:
            raise LimitExceeded(
                "max_subprocesses", self._subprocesses, self._policy.max_subprocesses
            )

    def check_file_change(self, path: str) -> None:
        self._check_killed()
        normalized = Path(path).as_posix().lstrip("./")
        if self._policy.allowed_paths:
            allowed = {
                Path(p).as_posix().lstrip("./").rstrip("/")
                for p in self._policy.allowed_paths
            }
            if not any(
                normalized == root or normalized.startswith(root + "/")
                for root in allowed
            ):
                raise LimitExceeded("allowed_paths", path, sorted(allowed))
        self._files_changed.add(normalized)
        count = len(self._files_changed)
        if count > self._policy.max_files_changed:
            raise LimitExceeded(
                "max_files_changed", count, self._policy.max_files_changed
            )

    def check_file_size(self, size_bytes: int) -> None:
        self._check_killed()
        if size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if size_bytes > self._policy.max_file_size_bytes:
            raise LimitExceeded(
                "max_file_size_bytes", size_bytes, self._policy.max_file_size_bytes
            )

    def check_duration(self) -> None:
        self._check_killed()
        assert self._start_time is not None
        elapsed = time.monotonic() - self._start_time
        if elapsed > self._policy.max_duration_seconds:
            raise LimitExceeded(
                "max_duration_seconds", elapsed, self._policy.max_duration_seconds
            )

    def check_pr_attempt(self) -> None:
        self._check_killed()
        self._pr_attempts += 1
        if self._pr_attempts > self._policy.max_pr_attempts:
            raise LimitExceeded(
                "max_pr_attempts", self._pr_attempts, self._policy.max_pr_attempts
            )

    def check_publication(self) -> None:
        self._check_killed()
        if not self._policy.allow_publication:
            raise LimitExceeded("allow_publication", False, True)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def summary(self) -> dict[str, Any]:
        elapsed = 0.0
        if self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
        return {
            "tool_calls": self._tool_calls,
            "subprocesses": self._subprocesses,
            "files_changed": len(self._files_changed),
            "pr_attempts": self._pr_attempts,
            "elapsed_time": elapsed,
            "killed": self._killed,
            "started": self._started,
        }
