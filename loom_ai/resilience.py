"""Failure-injection and recovery qualification (#816).

Provides a framework for injecting failures into system
components during testing and defining recovery policies
for each pipeline stage.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureMode(str, Enum):
    """Categories of failure to inject."""

    LLM_TIMEOUT = "llm_timeout"
    LLM_PARTIAL = "llm_partial"
    ARBITER_FAILURE = "arbiter_failure"
    DB_UNAVAILABLE = "db_unavailable"
    EMBEDDING_FAILURE = "embedding_failure"
    PROCESS_CRASH = "process_crash"
    GIT_PUSH_FAILURE = "git_push_failure"
    CANCELLATION = "cancellation"
    DUPLICATE_SUBMIT = "duplicate_submit"
    NETWORK_PARTITION = "network_partition"


@dataclass
class FailureInjection:
    """A single failure injection spec."""

    mode: FailureMode
    target: str
    probability: float
    delay_ms: int = 0
    error_msg: str = ""


class InjectedFailure(Exception):
    """Raised when an injection fires."""

    def __init__(
        self, injection: FailureInjection,
    ) -> None:
        self.injection = injection
        super().__init__(
            f"Injected {injection.mode.value}"
            f" at {injection.target}"
        )


class FailureInjector:
    """Injects failures into components for testing."""

    def __init__(self) -> None:
        self._injections: list[FailureInjection] = []
        self._triggered: list[dict[str, Any]] = []

    def add(
        self, injection: FailureInjection,
    ) -> None:
        """Register a failure injection."""
        self._injections.append(injection)

    def clear(self) -> None:
        """Remove all injections and history."""
        self._injections.clear()
        self._triggered.clear()

    def should_fail(
        self, target: str,
    ) -> FailureInjection | None:
        """Check if *target* should fail now."""
        for inj in self._injections:
            if (
                inj.target == target
                and random.random() < inj.probability
            ):
                self._triggered.append({
                    "mode": inj.mode.value,
                    "target": inj.target,
                    "timestamp": time.monotonic(),
                })
                return inj
        return None

    async def maybe_fail(self, target: str) -> None:
        """Raise :class:`InjectedFailure` if active."""
        inj = self.should_fail(target)
        if inj is not None:
            if inj.delay_ms > 0:
                await asyncio.sleep(
                    inj.delay_ms / 1000,
                )
            raise InjectedFailure(inj)

    @property
    def triggered(self) -> list[dict[str, Any]]:
        """Audit trail of triggered injections."""
        return list(self._triggered)


@dataclass
class RecoveryResult:
    """Outcome of a recovery attempt."""

    stage: str
    recovered: bool
    partial_data: dict[str, Any] = field(
        default_factory=dict,
    )
    error: str = ""
    duration_ms: float = 0.0


class RecoveryPolicy:
    """Per-stage failure handling policy."""

    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Any]] = {}

    def register(
        self,
        stage: str,
        *,
        retries: int = 0,
        idempotent: bool = False,
        preserves_partial: bool = False,
        requires_reconciliation: bool = False,
    ) -> None:
        """Define the recovery policy for *stage*."""
        self._policies[stage] = {
            "retries": retries,
            "idempotent": idempotent,
            "preserves_partial": preserves_partial,
            "requires_reconciliation": (
                requires_reconciliation
            ),
        }

    def get(self, stage: str) -> dict[str, Any]:
        """Return policy dict or empty dict."""
        return dict(self._policies.get(stage, {}))

    def should_retry(
        self, stage: str, attempt: int,
    ) -> bool:
        """True if *attempt* is within retry budget."""
        policy = self._policies.get(stage, {})
        return attempt <= policy.get("retries", 0)

    def is_idempotent(self, stage: str) -> bool:
        """True if the stage is safe to re-execute."""
        policy = self._policies.get(stage, {})
        return policy.get("idempotent", False)


def default_recovery_policies() -> RecoveryPolicy:
    """Standard policies for demo-agent stages."""
    rp = RecoveryPolicy()
    rp.register(
        "fetch", retries=2, idempotent=True,
    )
    rp.register(
        "plan", retries=1, idempotent=True,
    )
    rp.register(
        "implement",
        retries=2,
        preserves_partial=True,
    )
    rp.register(
        "review", retries=1, idempotent=True,
    )
    rp.register(
        "lint", retries=1, idempotent=True,
    )
    rp.register(
        "test", retries=1, idempotent=True,
    )
    rp.register(
        "persist", retries=2, idempotent=True,
    )
    rp.register(
        "git_push",
        retries=2,
        requires_reconciliation=True,
    )
    rp.register(
        "pr_create",
        retries=1,
        requires_reconciliation=True,
    )
    return rp
