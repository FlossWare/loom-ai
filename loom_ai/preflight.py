"""Dogfood environment preflight checker."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class Dependency(str, Enum):
    """External dependencies for dogfood runs."""

    PYTHON = "python"
    GIT = "git"
    GH_CLI = "gh_cli"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    LLM_API = "llm_api"
    GITHUB_TOKEN = "github_token"
    EMBEDDING_MODEL = "embedding_model"


class CheckStatus(str, Enum):
    """Result of a preflight check."""

    PASS = "pass"
    FAIL = "fail"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


@dataclass
class PreflightResult:
    """Outcome of a single preflight check."""

    dependency: Dependency
    status: CheckStatus
    required: bool
    message: str = ""
    version: str = ""


CheckFn = Callable[[], PreflightResult]


class PreflightChecker:
    """Run preflight checks before a dogfood run."""

    def __init__(self) -> None:
        self._checks: list[tuple[Dependency, bool, CheckFn]] = []
        self._register_defaults()

    def register(
        self,
        dep: Dependency,
        required: bool,
        check_fn: CheckFn,
    ) -> None:
        self._checks.append(
            (dep, required, check_fn),
        )

    def run_all(self) -> list[PreflightResult]:
        return [fn() for _, _, fn in self._checks]

    def is_ready(
        self,
        results: list[PreflightResult],
    ) -> bool:
        return all(r.status == CheckStatus.PASS for r in results if r.required)

    def summary(
        self,
        results: list[PreflightResult],
    ) -> dict[str, Any]:
        return {
            "ready": self.is_ready(results),
            "checks": [
                {
                    "dependency": r.dependency.value,
                    "status": r.status.value,
                    "required": r.required,
                    "message": r.message,
                    "version": r.version,
                }
                for r in results
            ],
        }

    def _register_defaults(self) -> None:
        self.register(
            Dependency.PYTHON,
            True,
            self.check_python,
        )
        self.register(
            Dependency.GIT,
            True,
            self.check_git,
        )
        self.register(
            Dependency.GH_CLI,
            False,
            self.check_gh_cli,
        )

    @staticmethod
    def check_python() -> PreflightResult:
        vi = sys.version_info
        ver = f"{vi.major}.{vi.minor}.{vi.micro}"
        if vi >= (3, 11):
            return PreflightResult(
                Dependency.PYTHON,
                CheckStatus.PASS,
                True,
                version=ver,
            )
        return PreflightResult(
            Dependency.PYTHON,
            CheckStatus.FAIL,
            True,
            message=f"Python >= 3.11 required, got {ver}",
            version=ver,
        )

    @staticmethod
    def check_git() -> PreflightResult:
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            ver = result.stdout.strip().replace(
                "git version ",
                "",
            )
            return PreflightResult(
                Dependency.GIT,
                CheckStatus.PASS,
                True,
                version=ver,
            )
        except FileNotFoundError:
            return PreflightResult(
                Dependency.GIT,
                CheckStatus.FAIL,
                True,
                message="git not found",
            )

    @staticmethod
    def check_gh_cli() -> PreflightResult:
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            first = result.stdout.strip().split("\n")[0]
            ver = first.replace("gh version ", "")
            return PreflightResult(
                Dependency.GH_CLI,
                CheckStatus.PASS,
                False,
                version=ver,
            )
        except FileNotFoundError:
            return PreflightResult(
                Dependency.GH_CLI,
                CheckStatus.DEGRADED,
                False,
                message="gh CLI not installed",
            )


@dataclass(frozen=True)
class EnvironmentSpec:
    """Defines the expected dogfood environment."""

    min_python: tuple[int, int] = (3, 11)
    required_deps: frozenset[Dependency] = frozenset(
        {Dependency.PYTHON, Dependency.GIT},
    )
    optional_deps: frozenset[Dependency] = frozenset(
        {Dependency.GH_CLI, Dependency.REDIS},
    )
