"""Tests for security capabilities (#814)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from loom_ai.backends.security import AuditLogger
from loom_ai.capabilities import (
    Capability,
    CapabilityGuard,
    SecretGuard,
    SubprocessPolicy,
)


@pytest.fixture
def audit():
    return AuditLogger()


@pytest.fixture
def guard(audit):
    return CapabilityGuard(audit)


@pytest.fixture
def secret_guard(audit):
    return SecretGuard(audit)


# 1. Grant and check (happy path)
def test_grant_and_check(guard, tmp_path):
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
    )
    assert guard.check(Capability.FS_READ, tmp_path)


# 2. Deny when capability not granted
def test_deny_not_granted(guard, tmp_path):
    assert not guard.check(
        Capability.FS_READ,
        tmp_path,
    )


# 3. Deny when workspace doesn't match
def test_deny_workspace_mismatch(guard, tmp_path):
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
    )
    other = tmp_path / "other"
    other.mkdir()
    assert not guard.check(
        Capability.FS_READ,
        other,
    )


# 4. Deny expired capability
def test_deny_expired(guard, tmp_path):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
        expires_at=past,
    )
    assert not guard.check(
        Capability.FS_READ,
        tmp_path,
    )


# 5. Subprocess allows valid command
def test_subprocess_allows_valid(guard, tmp_path):
    guard.grant(
        Capability.SUBPROCESS,
        tmp_path,
        {"allowed_cmds": ["ruff", "pytest"]},
        "test",
    )
    assert guard.check(
        Capability.SUBPROCESS,
        tmp_path,
        cmd="ruff",
    )


# 6. Subprocess denies unlisted command
def test_subprocess_denies_unlisted(guard, tmp_path):
    guard.grant(
        Capability.SUBPROCESS,
        tmp_path,
        {"allowed_cmds": ["ruff", "pytest"]},
        "test",
    )
    assert not guard.check(
        Capability.SUBPROCESS,
        tmp_path,
        cmd="rm",
    )


# 7. Path traversal denied
def test_path_traversal_denied(guard, tmp_path):
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
    )
    assert not guard.check(
        Capability.FS_READ,
        tmp_path,
        path="../../../etc/passwd",
    )


# 8. Symlink escape denied
def test_symlink_escape_denied(guard, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("sensitive data")

    inside = tmp_path / "sandbox"
    inside.mkdir()
    link = inside / "escape"
    link.symlink_to(outside)

    guard.grant(
        Capability.FS_READ,
        inside,
        {},
        "test",
    )
    assert not guard.check(
        Capability.FS_READ,
        inside,
        path="escape/secret.txt",
    )


# 9. GitHub write denied for wrong repo
def test_github_write_wrong_repo(guard, tmp_path):
    guard.grant(
        Capability.GITHUB_WRITE,
        tmp_path,
        {"allowed_repos": ["org/repo1"]},
        "test",
    )
    assert not guard.check(
        Capability.GITHUB_WRITE,
        tmp_path,
        repo="evil/repo",
    )


# 10. Secret access redacts in audit
def test_secret_redacts_in_audit(
    secret_guard,
    audit,
    monkeypatch,
):
    monkeypatch.setenv("MY_SECRET", "s3cr3tval")
    val = secret_guard.get("MY_SECRET")
    assert val == "s3cr3tval"
    entries = audit.find(action="secret_read")
    assert len(entries) == 1
    assert "s3cr3tval" not in entries[0].detail


# 11. Audit events for granted and denied
def test_audit_events(guard, audit, tmp_path):
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
    )
    guard.check(Capability.FS_READ, tmp_path)
    guard.check(Capability.FS_WRITE, tmp_path)
    allowed = [e for e in audit.entries if e.outcome == "allowed"]
    denied = [e for e in audit.entries if e.outcome == "denied"]
    assert len(allowed) == 1
    assert len(denied) == 1


# 12. require() raises PermissionError
def test_require_raises(guard, tmp_path):
    with pytest.raises(PermissionError, match="denied"):
        guard.require(
            Capability.FS_READ,
            tmp_path,
        )


# 13. Multiple capabilities granted
def test_multiple_capabilities(guard, tmp_path):
    guard.grant(
        Capability.FS_READ,
        tmp_path,
        {},
        "test",
    )
    guard.grant(
        Capability.FS_WRITE,
        tmp_path,
        {},
        "test",
    )
    guard.grant(
        Capability.GIT_READ,
        tmp_path,
        {},
        "test",
    )
    assert guard.check(Capability.FS_READ, tmp_path)
    assert guard.check(Capability.FS_WRITE, tmp_path)
    assert guard.check(Capability.GIT_READ, tmp_path)
    assert not guard.check(
        Capability.NETWORK,
        tmp_path,
    )


# 14. Expired grant ignored even with matching constraints
def test_expired_ignored_with_constraints(
    guard,
    tmp_path,
):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    guard.grant(
        Capability.SUBPROCESS,
        tmp_path,
        {"allowed_cmds": ["ruff"]},
        "test",
        expires_at=past,
    )
    assert not guard.check(
        Capability.SUBPROCESS,
        tmp_path,
        cmd="ruff",
    )


# Extra: SubprocessPolicy dataclass
def test_subprocess_policy_frozen():
    policy = SubprocessPolicy(
        allowed_commands=frozenset({"ruff", "pytest"}),
    )
    assert "ruff" in policy.allowed_commands
    assert policy.max_timeout == 300
    assert policy.max_output_bytes == 1_000_000


# Extra: SecretGuard tracks accessed secrets
def test_secret_guard_accessed(
    secret_guard,
    monkeypatch,
):
    monkeypatch.setenv("KEY_A", "val_a")
    monkeypatch.setenv("KEY_B", "val_b")
    secret_guard.get("KEY_A")
    secret_guard.get("KEY_B")
    assert secret_guard.accessed == frozenset(
        {"KEY_A", "KEY_B"},
    )


# Extra: SecretGuard raises on missing secret
def test_secret_guard_missing(secret_guard):
    with pytest.raises(KeyError, match="not found"):
        secret_guard.get("DOES_NOT_EXIST")


# Extra: GitHub write allows valid repo
def test_github_write_allowed(guard, tmp_path):
    guard.grant(
        Capability.GITHUB_WRITE,
        tmp_path,
        {"allowed_repos": ["FlossWare/loom-ai"]},
        "test",
    )
    assert guard.check(
        Capability.GITHUB_WRITE,
        tmp_path,
        repo="FlossWare/loom-ai",
    )


# Extra: FS write path traversal
def test_fs_write_traversal(guard, tmp_path):
    guard.grant(
        Capability.FS_WRITE,
        tmp_path,
        {},
        "test",
    )
    assert not guard.check(
        Capability.FS_WRITE,
        tmp_path,
        path="../../etc/shadow",
    )
