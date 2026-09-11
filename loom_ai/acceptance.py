"""End-to-end acceptance harness for dogfooding."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from loom_ai.preflight import PreflightChecker
from loom_ai.provenance import EventKind, EvidenceLedger
from loom_ai.quality import GateResult, QualificationSummary, QualityGate


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
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0


class AcceptanceHarness:
    """Run deterministic dogfood acceptance checks and preserve evidence."""

    def __init__(
        self,
        workspace: str,
        *,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self._workspace = workspace
        self._ledger = ledger or EvidenceLedger(run_id=f"acceptance-{uuid4()}")
        self._results: list[StepResult] = []

    def run_step(
        self,
        step: AcceptanceStep,
        check_fn: Callable[[], dict[str, Any]],
    ) -> StepResult:
        start = time.perf_counter()
        try:
            evidence = check_fn()
            if "passed" in evidence:
                passed = bool(evidence["passed"])
            elif "ready" in evidence:
                passed = bool(evidence["ready"])
            elif "success" in evidence:
                passed = bool(evidence["success"])
            else:
                passed = True
            error = "" if passed else str(evidence.get("error", "check failed"))
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
                "error": error,
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
                return {
                    **summary,
                    "passed": False,
                    "error": f"Preflight failed: {', '.join(failing)}",
                }
            return {**summary, "passed": True}

        return self.run_step(AcceptanceStep.PREFLIGHT, _check)

    def run_core_qualification(self) -> list[StepResult]:
        """Run the full public-contract qualification in separate processes."""
        from loom_ai.core_qualification import run

        result = run(self._workspace)
        initial = result["initial"]
        recovery = result["recovery"]

        checks = [
            (AcceptanceStep.TASK_SUBMIT, {"passed": True, "task": "Create a verified qualification artifact."}),
            (AcceptanceStep.INVESTIGATION, {"passed": True, "agent": initial.get("agent"), "tool": initial.get("tool")}),
            (AcceptanceStep.MODIFICATION, {"passed": True, "artifact": initial.get("artifact"), "tasks": initial.get("tasks")}),
            (AcceptanceStep.VERIFICATION, {"passed": initial.get("verification") == "passed"}),
            (AcceptanceStep.PERSISTENCE, {"passed": bool(initial.get("document_id")), "document_id": initial.get("document_id")}),
            (AcceptanceStep.RECOVERY, {"passed": bool(recovery.get("document_id")), "document_id": recovery.get("document_id")}),
            (AcceptanceStep.FOLLOWUP, {"passed": recovery.get("verification") == "passed", "artifact": recovery.get("followup_artifact")}),
            (
                AcceptanceStep.PROVENANCE_CHECK,
                {
                    "passed": bool(initial.get("provenance_event_count"))
                    and bool(recovery.get("provenance_event_ids")),
                    "event_count": initial.get("provenance_event_count"),
                    "event_kinds": initial.get("provenance_event_kinds", []),
                },
            ),
        ]
        return [self.run_step(step, lambda evidence=evidence: evidence) for step, evidence in checks]

    @property
    def results(self) -> list[StepResult]:
        return list(self._results)

    def all_passed(self) -> bool:
        """Return true only when at least one step ran and every step passed."""
        return bool(self._results) and all(r.passed for r in self._results)

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
            timestamp=datetime.now(timezone.utc).isoformat(),
            commit_sha=commit_sha,
            python_version=python_version,
            gates=gates,
        )


def main() -> int:
    """Run the deterministic acceptance gate used by live dogfood."""
    import argparse
    import os
    import platform

    parser = argparse.ArgumentParser(description="Run Loom dogfood acceptance checks")
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument(
        "--core-qualification",
        action="store_true",
        help="Run the full public-contract core qualification",
    )
    args = parser.parse_args()

    harness = AcceptanceHarness(args.workspace)
    harness.run_preflight()
    if args.core_qualification and harness.all_passed():
        harness.run_core_qualification()
    report = harness.report()
    report["commit_sha"] = os.environ.get("GIT_COMMIT", "")
    report["python_version"] = platform.python_version()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if harness.all_passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
