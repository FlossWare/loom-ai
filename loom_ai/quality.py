"""Quality gate definitions for CI and local use (#817)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Self


class QualityGate(str, Enum):
    """Individual quality gate checks."""

    LINT = "lint"
    FORMAT = "format"
    TESTS = "tests"
    COVERAGE = "coverage"
    IMPORTS = "imports"
    SECURITY_AUDIT = "security_audit"
    VERSION_FORMAT = "version_format"


@dataclass
class GateResult:
    """Outcome of a single quality gate."""

    gate: QualityGate
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class QualificationSummary:
    """Machine-readable build qualification report."""

    timestamp: str
    commit_sha: str
    python_version: str
    gates: list[GateResult] = field(default_factory=list)

    @property
    def qualified(self) -> bool:
        """True only when at least one required gate exists and all pass."""
        return bool(self.gates) and all(g.passed for g in self.gates)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "timestamp": self.timestamp,
            "commit_sha": self.commit_sha,
            "python_version": self.python_version,
            "qualified": self.qualified,
            "gates": [asdict(g) for g in self.gates],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Restore from a dict produced by to_dict."""
        gates = [
            GateResult(
                gate=QualityGate(g["gate"]),
                passed=bool(g["passed"]),
                detail=g.get("detail", ""),
                duration_ms=g.get("duration_ms", 0.0),
            )
            for g in d.get("gates", [])
        ]
        return cls(
            timestamp=d["timestamp"],
            commit_sha=d["commit_sha"],
            python_version=d["python_version"],
            gates=gates,
        )
