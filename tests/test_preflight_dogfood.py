from __future__ import annotations

from loom_ai.preflight import CheckStatus, Dependency, PreflightChecker


def test_postgresql_configuration_is_required(monkeypatch) -> None:
    monkeypatch.setenv("LOOM_STORAGE", "postgresql")
    checker = PreflightChecker()
    results = checker.run_all()
    pg = next(r for r in results if r.dependency == Dependency.POSTGRESQL)
    assert pg.required
    assert pg.status in (CheckStatus.PASS, CheckStatus.FAIL)


def test_llm_configuration_is_required(monkeypatch) -> None:
    monkeypatch.setenv("LOOM_LLM_BASE_URL", "http://llm:4000/v1")
    checker = PreflightChecker()
    results = checker.run_all()
    llm = next(r for r in results if r.dependency == Dependency.LLM_API)
    assert llm.required
    assert llm.status == CheckStatus.PASS


def test_non_noop_embedding_is_required(monkeypatch) -> None:
    monkeypatch.setenv("LOOM_EMBEDDING", "litellm")
    checker = PreflightChecker()
    results = checker.run_all()
    embedding = next(r for r in results if r.dependency == Dependency.EMBEDDING_MODEL)
    assert embedding.required
    assert embedding.status == CheckStatus.PASS


def test_required_github_cli_policy_is_honored(monkeypatch) -> None:
    monkeypatch.setenv("LOOM_REQUIRE_GITHUB", "1")
    result = PreflightChecker.check_gh_cli()
    assert result.required is True
    assert result.status in (CheckStatus.PASS, CheckStatus.FAIL)
