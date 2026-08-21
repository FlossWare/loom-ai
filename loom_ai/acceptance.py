"""End-to-end acceptance harness for dogfooding."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from loom_ai.preflight import PreflightChecker
from loom_ai.provenance import EventKind, EvidenceLedger
from loom_ai.quality import (
    GateResult,
    QualificationSummary,
    QualityGate,
)


class AcceptanceStep(str, Enum):
    PREFLIGHT = "preflight"
    TASK_SUBMIT = "task_submit"
    INVESTIGATION = "investigation"
    MODIFICATION = "modification"
    VERIFICATION = "verification"
    PERSISTENCE = "persistence"
    RECOVERY = "recovery"
    FOLLOWUP = "followup"
    PROVENANCE_CHECK = "provenance_check"


@dataclass
class StepResult:
    step: AcceptanceStep
    passed: bool
    evidence: dict[str, Any] = field(
        default_factory=dict,
    )
    error: str = ""
    duration_ms: float = 0.0


class AcceptanceHarness:
    def __init__(
        self,
        workspace: str,
        *,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self._workspace = workspace
        self._ledger = ledger or EvidenceLedger(
            run_id=f"acceptance-{uuid4()}",
        )
        self._results: list[StepResult] = []

    def run_step(
        self,
        step: AcceptanceStep,
        check_fn: Callable[[], dict[str, Any]],
    ) -> StepResult:
        start = time.perf_counter()
        try:
            evidence = check_fn()
            passed = True
            error = ""
        except Exception as exc:
            evidence = {}
            passed = False
            error = str(exc)
        duration_ms = (time.perf_counter() - start) * 1000
        result = StepResult(
            step=step,
            passed=passed,
            evidence=evidence,
            error=error,
            duration_ms=duration_ms,
        )
        self._results.append(result)
        self._ledger.record(
            kind=EventKind.VERIFICATION_RUN,
            payload={
                "step": step.value,
                "passed": passed,
                **evidence,
            },
        )
        return result

    def run_preflight(self) -> StepResult:
        checker = PreflightChecker()
        results = checker.run_all()
        summary = checker.summary(results)

        def _check() -> dict[str, Any]:
            if not summary["ready"]:
                failing = [
                    c["dependency"]
                    for c in summary["checks"]
                    if c["status"] != "pass" and c["required"]
                ]
                raise RuntimeError(f"Preflight failed: {', '.join(failing)}")
            return summary

        return self.run_step(
            AcceptanceStep.PREFLIGHT,
            _check,
        )

    @property
    def results(self) -> list[StepResult]:
        return list(self._results)

    def all_passed(self) -> bool:
        return all(r.passed for r in self._results)

    def report(self) -> dict[str, Any]:
        return {
            "results": [
                {
                    "step": r.step.value,
                    "passed": r.passed,
                    "evidence": r.evidence,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in self._results
            ],
            "all_passed": self.all_passed(),
        }

    def to_qualification(
        self,
        *,
        commit_sha: str = "",
        python_version: str = "",
    ) -> QualificationSummary:
        gates = [
            GateResult(
                gate=QualityGate.TESTS,
                passed=r.passed,
                detail=r.step.value,
                duration_ms=r.duration_ms,
            )
            for r in self._results
        ]
        return QualificationSummary(
            timestamp=datetime.now(
                timezone.utc,
            ).isoformat(),
            commit_sha=commit_sha,
            python_version=python_version,
            gates=gates,
        )
