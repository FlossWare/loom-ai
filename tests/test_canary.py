"""Tests for canary mode and kill-switch."""

from __future__ import annotations

import time

import pytest

from loom_ai.canary import (
    CanaryGuard,
    CanaryPolicy,
    KillSwitchActive,
    LimitExceeded,
)


def test_canary_policy_defaults():
    p = CanaryPolicy()
    assert p.max_files_changed == 5
    assert p.max_file_size_bytes == 50_000
    assert p.max_tool_calls == 50
    assert p.max_subprocesses == 10
    assert p.max_duration_seconds == 300
    assert p.max_retries == 3
    assert p.max_concurrent_workers == 2
    assert p.max_pr_attempts == 1
    assert p.allowed_paths == frozenset()
    assert p.require_human_approval is True
    assert p.allow_publication is False


def test_start_records_time():
    g = CanaryGuard(CanaryPolicy())
    g.start()
    s = g.summary()
    assert s["elapsed_time"] >= 0


def test_tool_call_limit():
    g = CanaryGuard(CanaryPolicy(max_tool_calls=2))
    g.start()
    g.check_tool_call()
    g.check_tool_call()
    with pytest.raises(LimitExceeded):
        g.check_tool_call()


def test_subprocess_limit():
    g = CanaryGuard(CanaryPolicy(max_subprocesses=2))
    g.start()
    g.check_subprocess()
    g.check_subprocess()
    with pytest.raises(LimitExceeded):
        g.check_subprocess()


def test_file_change_count_limit():
    g = CanaryGuard(
        CanaryPolicy(max_files_changed=2),
    )
    g.start()
    g.check_file_change("a.py")
    g.check_file_change("b.py")
    with pytest.raises(LimitExceeded):
        g.check_file_change("c.py")


def test_file_change_allowed_paths():
    g = CanaryGuard(
        CanaryPolicy(
            allowed_paths=frozenset({"ok.py"}),
        ),
    )
    g.start()
    g.check_file_change("ok.py")
    with pytest.raises(LimitExceeded):
        g.check_file_change("nope.py")


def test_file_size_limit():
    g = CanaryGuard(
        CanaryPolicy(max_file_size_bytes=100),
    )
    g.start()
    g.check_file_size(50)
    with pytest.raises(LimitExceeded):
        g.check_file_size(200)


def test_duration_limit():
    g = CanaryGuard(
        CanaryPolicy(max_duration_seconds=0),
    )
    g.start()
    time.sleep(0.01)
    with pytest.raises(LimitExceeded):
        g.check_duration()


def test_pr_attempt_limit():
    g = CanaryGuard(CanaryPolicy(max_pr_attempts=1))
    g.start()
    g.check_pr_attempt()
    with pytest.raises(LimitExceeded):
        g.check_pr_attempt()


def test_publication_not_allowed():
    g = CanaryGuard(
        CanaryPolicy(allow_publication=False),
    )
    g.start()
    with pytest.raises(LimitExceeded):
        g.check_publication()


def test_publication_allowed():
    g = CanaryGuard(
        CanaryPolicy(allow_publication=True),
    )
    g.start()
    g.check_publication()


def test_kill_sets_flag_and_emits():
    g = CanaryGuard(CanaryPolicy())
    g.start()
    g.kill("test reason")
    assert g.is_killed is True
    # start + kill both emit structured events (A+ observability)
    assert len(g.events) == 2
    assert g.events[0]["type"] == "start"
    assert g.events[1]["type"] == "kill"
    assert g.events[1]["reason"] == "test reason"


def test_all_checks_raise_after_kill():
    g = CanaryGuard(CanaryPolicy())
    g.start()
    g.kill()
    with pytest.raises(KillSwitchActive):
        g.check_tool_call()
    with pytest.raises(KillSwitchActive):
        g.check_subprocess()
    with pytest.raises(KillSwitchActive):
        g.check_file_change("x")
    with pytest.raises(KillSwitchActive):
        g.check_file_size(1)
    with pytest.raises(KillSwitchActive):
        g.check_duration()
    with pytest.raises(KillSwitchActive):
        g.check_pr_attempt()
    with pytest.raises(KillSwitchActive):
        g.check_publication()


def test_summary_returns_state():
    g = CanaryGuard(CanaryPolicy())
    g.start()
    g.check_tool_call()
    g.check_subprocess()
    g.check_file_change("f.py")
    s = g.summary()
    assert s["tool_calls"] == 1
    assert s["subprocesses"] == 1
    assert s["files_changed"] == 1
    assert s["pr_attempts"] == 0
    assert s["killed"] is False


def test_limit_exceeded_attributes():
    exc = LimitExceeded("test", 10, 5)
    assert exc.limit_name == "test"
    assert exc.value == 10
    assert exc.max_value == 5
