"""Tests for security hardening: ConfigValidator, SecretsMask,
AuditLogger, and PolicyOverride.
"""

from datetime import datetime, timedelta, timezone

from loom_ai.backends.security import (
    AuditLogger,
    ConfigValidator,
    PolicyOverride,
    SecretsMask,
)

# ── ConfigValidator ───────────────────────────────────────────────────────


def test_validator_valid_config():
    schema = {"host": str, "port": int, "debug": bool}
    v = ConfigValidator(schema)
    result = v.validate({"host": "localhost", "port": 8080, "debug": False})
    assert result.valid is True
    assert result.errors == []


def test_validator_missing_key():
    schema = {"host": str, "port": int}
    v = ConfigValidator(schema)
    result = v.validate({"host": "localhost"})
    assert result.valid is False
    assert any("missing required key: port" in e for e in result.errors)


def test_validator_wrong_type():
    schema = {"port": int}
    v = ConfigValidator(schema)
    result = v.validate({"port": "not-a-number"})
    assert result.valid is False
    assert any("expected int" in e for e in result.errors)


def test_validator_extra_keys_allowed():
    schema = {"host": str}
    v = ConfigValidator(schema)
    result = v.validate({"host": "localhost", "extra": 42})
    assert result.valid is True


def test_validator_multiple_errors():
    schema = {"host": str, "port": int, "workers": list}
    v = ConfigValidator(schema)
    result = v.validate({"host": 123})
    assert result.valid is False
    assert len(result.errors) == 3  # wrong type + 2 missing


def test_validator_empty_schema():
    v = ConfigValidator({})
    result = v.validate({"anything": "goes"})
    assert result.valid is True


# ── SecretsMask ───────────────────────────────────────────────────────────


def test_mask_api_key():
    mask = SecretsMask()
    text = "api_key=sk-abc123xyz"
    result = mask.redact(text)
    assert "sk-abc123xyz" not in result
    assert "***REDACTED***" in result


def test_mask_password():
    mask = SecretsMask()
    text = "password: my-super-secret"
    result = mask.redact(text)
    assert "my-super-secret" not in result
    assert "***REDACTED***" in result


def test_mask_bearer_token():
    mask = SecretsMask()
    text = "Authorization: Bearer eyJhbGciOiJI.token.here"
    result = mask.redact(text)
    assert "eyJhbGciOiJI" not in result
    assert "***REDACTED***" in result


def test_mask_preserves_label():
    mask = SecretsMask()
    text = "api_key=secret123"
    result = mask.redact(text)
    assert result.startswith("api_key=")


def test_mask_custom_placeholder():
    mask = SecretsMask(placeholder="[HIDDEN]")
    text = "token=abc123"
    result = mask.redact(text)
    assert "[HIDDEN]" in result


def test_mask_custom_pattern():
    mask = SecretsMask(patterns=[r"(ssn\s*=\s*)\d{3}-\d{2}-\d{4}"])
    text = "ssn = 123-45-6789"
    result = mask.redact(text)
    assert "123-45-6789" not in result


def test_mask_no_secrets_unchanged():
    mask = SecretsMask()
    text = "Hello, this is a normal log line."
    assert mask.redact(text) == text


def test_mask_multiple_secrets():
    mask = SecretsMask()
    text = "api_key=abc123 password=hunter2"
    result = mask.redact(text)
    assert "abc123" not in result
    assert "hunter2" not in result


# ── AuditLogger ───────────────────────────────────────────────────────────


def test_audit_log_creates_entry():
    logger = AuditLogger()
    entry = logger.log(actor="admin", action="login", resource="system")
    assert entry.actor == "admin"
    assert entry.action == "login"
    assert entry.resource == "system"
    assert entry.outcome == "success"
    assert entry.timestamp != ""


def test_audit_log_custom_outcome():
    logger = AuditLogger()
    entry = logger.log(
        actor="user1",
        action="delete",
        resource="config",
        outcome="denied",
        detail="insufficient permissions",
    )
    assert entry.outcome == "denied"
    assert entry.detail == "insufficient permissions"


def test_audit_entries_ordered():
    logger = AuditLogger()
    logger.log(actor="a", action="first", resource="r")
    logger.log(actor="b", action="second", resource="r")
    entries = logger.entries
    assert len(entries) == 2
    assert entries[0].action == "first"
    assert entries[1].action == "second"


def test_audit_entries_returns_copy():
    logger = AuditLogger()
    logger.log(actor="a", action="x", resource="r")
    entries = logger.entries
    entries.clear()
    assert len(logger.entries) == 1  # original unaffected


def test_audit_find_by_actor():
    logger = AuditLogger()
    logger.log(actor="admin", action="read", resource="config")
    logger.log(actor="user1", action="write", resource="config")
    results = logger.find(actor="admin")
    assert len(results) == 1
    assert results[0].actor == "admin"


def test_audit_find_by_action():
    logger = AuditLogger()
    logger.log(actor="a", action="login", resource="r")
    logger.log(actor="b", action="logout", resource="r")
    results = logger.find(action="login")
    assert len(results) == 1


def test_audit_find_by_resource():
    logger = AuditLogger()
    logger.log(actor="a", action="read", resource="secrets")
    logger.log(actor="a", action="read", resource="config")
    results = logger.find(resource="secrets")
    assert len(results) == 1


def test_audit_find_combined_filters():
    logger = AuditLogger()
    logger.log(actor="admin", action="read", resource="secrets")
    logger.log(actor="admin", action="write", resource="secrets")
    logger.log(actor="user1", action="read", resource="secrets")
    results = logger.find(actor="admin", action="read")
    assert len(results) == 1


def test_audit_find_no_match():
    logger = AuditLogger()
    logger.log(actor="admin", action="read", resource="config")
    results = logger.find(actor="ghost")
    assert results == []


# ── PolicyOverride ────────────────────────────────────────────────────────


def _future(minutes: int = 60) -> str:
    """Return an ISO timestamp *minutes* from now."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _past(minutes: int = 60) -> str:
    """Return an ISO timestamp *minutes* ago."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def test_override_set_and_get():
    po = PolicyOverride()
    po.set("max_workers", 10, actor="admin", reason="load test", expires_at=_future())
    assert po.get("max_workers") == 10


def test_override_expired_returns_none():
    po = PolicyOverride()
    po.set("max_workers", 10, actor="admin", reason="done", expires_at=_past())
    assert po.get("max_workers") is None


def test_override_missing_returns_none():
    po = PolicyOverride()
    assert po.get("nonexistent") is None


def test_override_revoke():
    po = PolicyOverride()
    po.set("debug", True, actor="admin", reason="debugging", expires_at=_future())
    assert po.revoke("debug") is True
    assert po.get("debug") is None


def test_override_revoke_missing():
    po = PolicyOverride()
    assert po.revoke("ghost") is False


def test_override_replace():
    po = PolicyOverride()
    po.set("max_workers", 5, actor="admin", reason="v1", expires_at=_future())
    po.set("max_workers", 20, actor="admin", reason="v2", expires_at=_future())
    assert po.get("max_workers") == 20


def test_active_overrides_excludes_expired():
    po = PolicyOverride()
    po.set("active", True, actor="a", reason="r", expires_at=_future())
    po.set("expired", True, actor="a", reason="r", expires_at=_past())
    active = po.active_overrides()
    assert len(active) == 1
    assert active[0].policy == "active"


def test_override_created_at_populated():
    po = PolicyOverride()
    override = po.set("flag", True, actor="admin", reason="test", expires_at=_future())
    assert override.created_at != ""
