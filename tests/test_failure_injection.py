"""Tests for failure-injection and recovery (#816)."""

from __future__ import annotations

import asyncio

import pytest

from loom_ai.resilience import (
    FailureInjection,
    FailureInjector,
    FailureMode,
    InjectedFailure,
    RecoveryPolicy,
    RecoveryResult,
    default_recovery_policies,
)


# 1. probability=1.0 always triggers
async def test_always_triggers():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=1.0,
        )
    )
    with pytest.raises(InjectedFailure):
        await inj.maybe_fail("llm")


# 2. probability=0.0 never triggers
async def test_never_triggers():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=0.0,
        )
    )
    await inj.maybe_fail("llm")


# 3. InjectedFailure contains injection
def test_injected_failure_info():
    fi = FailureInjection(
        mode=FailureMode.DB_UNAVAILABLE,
        target="db",
        probability=1.0,
    )
    exc = InjectedFailure(fi)
    assert exc.injection is fi
    assert "db_unavailable" in str(exc)
    assert "db" in str(exc)


# 4. maybe_fail raises InjectedFailure
async def test_maybe_fail_raises():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.GIT_PUSH_FAILURE,
            target="git",
            probability=1.0,
        )
    )
    with pytest.raises(InjectedFailure) as exc_info:
        await inj.maybe_fail("git")
    assert exc_info.value.injection.mode == FailureMode.GIT_PUSH_FAILURE


# 5. maybe_fail with delay adds latency
async def test_maybe_fail_delay():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.NETWORK_PARTITION,
            target="net",
            probability=1.0,
            delay_ms=200,
        )
    )
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    with pytest.raises(InjectedFailure):
        await inj.maybe_fail("net")
    elapsed = loop.time() - t0
    assert elapsed >= 0.15


# 6. RecoveryPolicy registers and retrieves
def test_recovery_policy_register():
    rp = RecoveryPolicy()
    rp.register(
        "fetch",
        retries=2,
        idempotent=True,
    )
    p = rp.get("fetch")
    assert p["retries"] == 2
    assert p["idempotent"] is True


# 7. should_retry respects limit
def test_should_retry():
    rp = RecoveryPolicy()
    rp.register("fetch", retries=2)
    assert rp.should_retry("fetch", 1)
    assert rp.should_retry("fetch", 2)
    assert not rp.should_retry("fetch", 3)


# 8. is_idempotent
def test_is_idempotent():
    rp = RecoveryPolicy()
    rp.register("fetch", idempotent=True)
    rp.register("implement")
    assert rp.is_idempotent("fetch")
    assert not rp.is_idempotent("implement")
    assert not rp.is_idempotent("unknown")


# 9. default policies cover all stages
def test_default_policies():
    rp = default_recovery_policies()
    stages = [
        "fetch",
        "plan",
        "implement",
        "review",
        "lint",
        "test",
        "persist",
        "git_push",
        "pr_create",
    ]
    for stage in stages:
        p = rp.get(stage)
        assert p, f"missing policy for {stage}"
    assert rp.get("fetch")["retries"] == 2
    assert rp.get("fetch")["idempotent"] is True
    assert rp.get("implement")["preserves_partial"]
    assert rp.get("git_push")["requires_reconciliation"]


# 10. triggered audit trail
async def test_triggered_audit():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=1.0,
        )
    )
    try:
        await inj.maybe_fail("llm")
    except InjectedFailure:
        pass
    assert len(inj.triggered) == 1
    assert inj.triggered[0]["target"] == "llm"
    assert inj.triggered[0]["mode"] == "llm_timeout"
    assert "timestamp" in inj.triggered[0]


# 11. clear removes all
def test_clear():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=1.0,
        )
    )
    assert inj.should_fail("llm") is not None
    inj.clear()
    assert inj.should_fail("llm") is None
    assert inj.triggered == []


# 12. Multiple injections for different targets
async def test_multiple_targets():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=1.0,
        )
    )
    inj.add(
        FailureInjection(
            mode=FailureMode.DB_UNAVAILABLE,
            target="db",
            probability=1.0,
        )
    )
    with pytest.raises(InjectedFailure) as e1:
        await inj.maybe_fail("llm")
    assert e1.value.injection.mode == FailureMode.LLM_TIMEOUT
    with pytest.raises(InjectedFailure) as e2:
        await inj.maybe_fail("db")
    assert e2.value.injection.mode == FailureMode.DB_UNAVAILABLE
    await inj.maybe_fail("other")


# 13. RecoveryResult captures partial data
def test_recovery_result():
    r = RecoveryResult(
        stage="implement",
        recovered=True,
        partial_data={"files_applied": 2},
        duration_ms=1500.0,
    )
    assert r.recovered
    assert r.partial_data["files_applied"] == 2
    assert r.duration_ms == 1500.0
    assert r.error == ""


# 14. FailureMode has all 10 modes
def test_failure_mode_completeness():
    assert len(FailureMode) == 10
    expected = {
        "llm_timeout",
        "llm_partial",
        "arbiter_failure",
        "db_unavailable",
        "embedding_failure",
        "process_crash",
        "git_push_failure",
        "cancellation",
        "duplicate_submit",
        "network_partition",
    }
    actual = {m.value for m in FailureMode}
    assert actual == expected


# Extra: unregistered stage returns empty
def test_unknown_stage():
    rp = RecoveryPolicy()
    assert rp.get("nope") == {}
    assert not rp.should_retry("nope", 1)
    assert not rp.is_idempotent("nope")


# Extra: non-matching target doesn't trigger
async def test_target_mismatch():
    inj = FailureInjector()
    inj.add(
        FailureInjection(
            mode=FailureMode.LLM_TIMEOUT,
            target="llm",
            probability=1.0,
        )
    )
    await inj.maybe_fail("db")
    assert len(inj.triggered) == 0
