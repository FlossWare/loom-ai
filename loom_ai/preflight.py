"""Dogfood environment preflight checker."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse


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
    """Run preflight checks before a dogfood run.

    The defaults are derived from the configured Loom backends. A configured
    production dependency is never silently treated as optional.
    """

    def __init__(self) -> None:
        self._checks: list[tuple[Dependency, bool, CheckFn]] = []
        self._register_defaults()

    def register(self, dep: Dependency, required: bool, check_fn: CheckFn) -> None:
        self._checks.append((dep, required, check_fn))

    def run_all(self) -> list[PreflightResult]:
        return [fn() for _, _, fn in self._checks]

    def is_ready(self, results: list[PreflightResult]) -> bool:
        return all(
            r.status == CheckStatus.PASS
            for r in results
            if r.required
        )

    def summary(self, results: list[PreflightResult]) -> dict[str, Any]:
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
        self.register(Dependency.PYTHON, True, self.check_python)
        self.register(Dependency.GIT, True, self.check_git)

        storage = os.environ.get("LOOM_STORAGE", "memory")
        queue = os.environ.get("LOOM_QUEUE", "memory")
        embedding = os.environ.get("LOOM_EMBEDDING", "noop")
        llm_provider = os.environ.get("LOOM_LLM_PROVIDER", "openai-compatible")
        llm_url = os.environ.get("LOOM_LLM_BASE_URL", "")
        needs_llm = bool(llm_url) or llm_provider == "free"

        if storage == "postgresql":
            self.register(Dependency.POSTGRESQL, True, self.check_postgresql)
        if queue == "redis":
            self.register(Dependency.REDIS, True, self.check_redis)
        if embedding != "noop":
            self.register(Dependency.EMBEDDING_MODEL, True, self.check_embedding)
        if needs_llm:
            self.register(Dependency.LLM_API, True, self.check_llm)

        # The DemoAgent uses gh for issue retrieval and PR creation. Require
        # either the CLI or an explicit token when the operator configured a
        # GitHub-backed workflow.
        if os.environ.get("LOOM_REQUIRE_GITHUB", "0") == "1":
            self.register(Dependency.GH_CLI, True, self.check_gh_cli)
            self.register(Dependency.GITHUB_TOKEN, True, self.check_github_token)
        else:
            self.register(Dependency.GH_CLI, False, self.check_gh_cli)

    @staticmethod
    def check_python() -> PreflightResult:
        vi = sys.version_info
        ver = f"{vi.major}.{vi.minor}.{vi.micro}"
        if vi >= (3, 11):
            return PreflightResult(Dependency.PYTHON, CheckStatus.PASS, True, version=ver)
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
            ver = result.stdout.strip().replace("git version ", "")
            return PreflightResult(Dependency.GIT, CheckStatus.PASS, True, version=ver)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return PreflightResult(
                Dependency.GIT,
                CheckStatus.FAIL,
                True,
                message=f"git unavailable: {exc}",
            )

    @staticmethod
    def _check_tcp(
        dep: Dependency,
        host: str,
        port: int,
    ) -> PreflightResult:
        try:
            with socket.create_connection((host, port), timeout=2):
                return PreflightResult(dep, CheckStatus.PASS, True, version=f"{host}:{port}")
        except OSError as exc:
            return PreflightResult(
                dep,
                CheckStatus.FAIL,
                True,
                message=f"cannot connect to {host}:{port}: {exc}",
            )

    @classmethod
    def check_postgresql(cls) -> PreflightResult:
        host = os.environ.get("LOOM_PG_HOST", "localhost")
        try:
            port = int(os.environ.get("LOOM_PG_PORT", "5432"))
        except ValueError:
            return PreflightResult(
                Dependency.POSTGRESQL,
                CheckStatus.FAIL,
                True,
                message="LOOM_PG_PORT must be an integer",
            )
        return cls._check_tcp(Dependency.POSTGRESQL, host, port)

    @classmethod
    def check_redis(cls) -> PreflightResult:
        host = os.environ.get("LOOM_REDIS_HOST", "localhost")
        try:
            port = int(os.environ.get("LOOM_REDIS_PORT", "6379"))
        except ValueError:
            return PreflightResult(
                Dependency.REDIS,
                CheckStatus.FAIL,
                True,
                message="LOOM_REDIS_PORT must be an integer",
            )
        return cls._check_tcp(Dependency.REDIS, host, port)

    @staticmethod
    def check_llm() -> PreflightResult:
        provider = os.environ.get("LOOM_LLM_PROVIDER", "openai-compatible")
        if provider == "free":
            return PreflightResult(
                Dependency.LLM_API,
                CheckStatus.PASS,
                True,
                message="FreeModelRouter configured",
            )
        url = os.environ.get("LOOM_LLM_BASE_URL", "")
        if not url:
            return PreflightResult(
                Dependency.LLM_API,
                CheckStatus.FAIL,
                True,
                message="LOOM_LLM_BASE_URL is required",
            )
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return PreflightResult(
                Dependency.LLM_API,
                CheckStatus.FAIL,
                True,
                message="LOOM_LLM_BASE_URL must be an absolute http(s) URL",
            )
        return PreflightResult(Dependency.LLM_API, CheckStatus.PASS, True, version=url)

    @staticmethod
    def check_embedding() -> PreflightResult:
        kind = os.environ.get("LOOM_EMBEDDING", "noop")
        if kind == "noop":
            return PreflightResult(
                Dependency.EMBEDDING_MODEL,
                CheckStatus.FAIL,
                True,
                message="noop embeddings are not valid for persistent dogfood qualification",
            )
        if kind not in {"openai", "litellm"}:
            return PreflightResult(
                Dependency.EMBEDDING_MODEL,
                CheckStatus.FAIL,
                True,
                message=f"unsupported embedding backend: {kind}",
            )
        return PreflightResult(
            Dependency.EMBEDDING_MODEL,
            CheckStatus.PASS,
            True,
            version=kind,
        )

    @staticmethod
    def check_github_token() -> PreflightResult:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            return PreflightResult(
                Dependency.GITHUB_TOKEN,
                CheckStatus.FAIL,
                True,
                message="GITHUB_TOKEN or GH_TOKEN is required",
            )
        return PreflightResult(Dependency.GITHUB_TOKEN, CheckStatus.PASS, True)

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
            return PreflightResult(Dependency.GH_CLI, CheckStatus.PASS, False, version=ver)
        except (FileNotFoundError, subprocess.CalledProcessError):
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
