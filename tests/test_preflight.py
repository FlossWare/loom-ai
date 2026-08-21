"""Tests for dogfood environment preflight checker."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from loom_ai.preflight import (
    CheckStatus,
    Dependency,
    EnvironmentSpec,
    PreflightChecker,
    PreflightResult,
)


def test_check_python_passes():
    result = PreflightChecker.check_python()
    assert result.status == CheckStatus.PASS
    assert result.dependency == Dependency.PYTHON
    assert result.version


def test_check_git_finds_git():
    result = PreflightChecker.check_git()
    assert result.status == CheckStatus.PASS
    assert result.version


def test_check_gh_cli():
    result = PreflightChecker.check_gh_cli()
    assert result.status in (
        CheckStatus.PASS,
        CheckStatus.DEGRADED,
    )


def test_register_adds_custom_check():
    checker = PreflightChecker()

    def custom() -> PreflightResult:
        return PreflightResult(
            Dependency.LLM_API,
            CheckStatus.PASS,
            True,
        )

    checker.register(Dependency.LLM_API, True, custom)
    results = checker.run_all()
    deps = [r.dependency for r in results]
    assert Dependency.LLM_API in deps


def test_run_all_returns_results():
    checker = PreflightChecker()
    results = checker.run_all()
    assert len(results) >= 3


def test_is_ready_true_all_required_pass():
    checker = PreflightChecker()
    results = checker.run_all()
    assert checker.is_ready(results) is True


def test_is_ready_false_when_required_fails():
    checker = PreflightChecker()
    results = [
        PreflightResult(
            Dependency.PYTHON,
            CheckStatus.FAIL,
            True,
            message="too old",
        ),
    ]
    assert checker.is_ready(results) is False


def test_summary_machine_readable():
    checker = PreflightChecker()
    results = checker.run_all()
    s = checker.summary(results)
    assert isinstance(s, dict)
    assert "ready" in s
    assert "checks" in s
    assert isinstance(s["checks"], list)
    assert s["checks"][0]["dependency"] == "python"


def test_environment_spec_defaults():
    spec = EnvironmentSpec()
    assert spec.min_python == (3, 11)
    assert Dependency.PYTHON in spec.required_deps
    assert Dependency.GIT in spec.required_deps
    assert Dependency.GH_CLI in spec.optional_deps
    assert Dependency.REDIS in spec.optional_deps


def test_degraded_for_optional_missing():
    result = PreflightResult(
        Dependency.REDIS,
        CheckStatus.DEGRADED,
        False,
        message="redis not available",
    )
    assert result.status == CheckStatus.DEGRADED
    assert result.required is False


def test_custom_check_function():
    checker = PreflightChecker()

    def always_fail() -> PreflightResult:
        return PreflightResult(
            Dependency.POSTGRESQL,
            CheckStatus.FAIL,
            True,
            message="no pg",
        )

    checker.register(
        Dependency.POSTGRESQL,
        True,
        always_fail,
    )
    results = checker.run_all()
    assert checker.is_ready(results) is False


def test_preflight_result_fields():
    r = PreflightResult(
        dependency=Dependency.GIT,
        status=CheckStatus.PASS,
        required=True,
        message="ok",
        version="2.40.0",
    )
    assert r.dependency == Dependency.GIT
    assert r.status == CheckStatus.PASS
    assert r.required is True
    assert r.message == "ok"
    assert r.version == "2.40.0"


def test_environment_spec_frozen():
    spec = EnvironmentSpec()
    with pytest.raises(FrozenInstanceError):
        spec.min_python = (4, 0)  # type: ignore[misc]
