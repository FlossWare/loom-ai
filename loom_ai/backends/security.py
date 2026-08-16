"""Security hardening utilities for loom-ai.

Provides in-memory implementations for configuration validation, secret
redaction, audit logging, and temporary policy overrides.  All classes
are dependency-free and suitable for testing.

Classes
-------
ConfigValidator -- validate a config dict against a required-keys schema
SecretsMask -- redact sensitive values from text using regex patterns
AuditLogger -- append-only log of security-relevant events
PolicyOverride -- temporary policy overrides with automatic expiry
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── data models ──────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of a configuration validation check."""

    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class AuditEntry:
    """A single audit-log record."""

    timestamp: str
    actor: str
    action: str
    resource: str
    detail: str = ""
    outcome: str = "success"


@dataclass
class Override:
    """A temporary policy override with an expiry timestamp."""

    policy: str
    value: Any
    actor: str
    reason: str
    expires_at: str
    created_at: str = ""


# ── ConfigValidator ──────────────────────────────────────────────────────


class ConfigValidator:
    """Validate configuration dicts against a simple schema.

    The schema is a mapping of ``key -> type`` where *type* is a Python
    built-in type (``str``, ``int``, ``float``, ``bool``, ``list``,
    ``dict``).  Keys present in the schema are required; extra keys in
    the config are allowed.
    """

    def __init__(self, schema: dict[str, type]) -> None:
        self._schema = dict(schema)

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        """Check *config* against the schema.

        Returns a :class:`ValidationResult` with ``valid=True`` when all
        required keys are present and have the expected type.
        """
        errors: list[str] = []
        for key, expected_type in self._schema.items():
            if key not in config:
                errors.append(f"missing required key: {key}")
            elif expected_type in (int, float) and isinstance(config[key], bool):
                errors.append(
                    f"key '{key}' expected {expected_type.__name__}, got bool"
                )
            elif not isinstance(config[key], expected_type):
                actual = type(config[key]).__name__
                errors.append(
                    f"key '{key}' expected {expected_type.__name__}, got {actual}"
                )
        return ValidationResult(valid=len(errors) == 0, errors=errors)


# ── SecretsMask ──────────────────────────────────────────────────────────


class SecretsMask:
    """Redact secrets from text using configurable regex patterns.

    Each pattern is compiled once at construction time.  The
    ``redact`` method replaces every match with a fixed placeholder
    (default ``***REDACTED***``).
    """

    DEFAULT_PATTERNS: list[str] = [
        r"(?i)(api[_-]?key\s*[:=]\s*)\S+",
        r"(?i)(secret\s*[:=]\s*)\S+",
        r"(?i)(password\s*[:=]\s*)\S+",
        r"(?i)(token\s*[:=]\s*)\S+",
        r"(?i)(bearer\s+)\S+",
    ]

    def __init__(
        self,
        patterns: list[str] | None = None,
        placeholder: str = "***REDACTED***",
    ) -> None:
        raw = patterns if patterns is not None else self.DEFAULT_PATTERNS
        self._patterns = [re.compile(p) for p in raw]
        self._placeholder = placeholder

    def redact(self, text: str) -> str:
        """Return *text* with all matched secrets replaced."""
        result = text
        for pattern in self._patterns:
            result = pattern.sub(self._replacement, result)
        return result

    def _replacement(self, match: re.Match) -> str:  # type: ignore[type-arg]
        """Preserve the label prefix (group 1) and mask the value."""
        if match.lastindex and match.lastindex >= 1:
            return match.group(1) + self._placeholder
        return self._placeholder


# ── AuditLogger ──────────────────────────────────────────────────────────


class AuditLogger:
    """Append-only, in-memory audit log for security-relevant events.

    Every entry records a UTC timestamp, an actor, an action, the
    affected resource, optional detail text, and an outcome.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def log(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        detail: str = "",
        outcome: str = "success",
    ) -> AuditEntry:
        """Record a new audit event and return the entry."""
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            outcome=outcome,
        )
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        """All recorded entries (oldest first)."""
        return list(self._entries)

    def find(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
    ) -> list[AuditEntry]:
        """Filter entries by actor, action, and/or resource."""
        results = self._entries
        if actor is not None:
            results = [e for e in results if e.actor == actor]
        if action is not None:
            results = [e for e in results if e.action == action]
        if resource is not None:
            results = [e for e in results if e.resource == resource]
        return results


# ── PolicyOverride ───────────────────────────────────────────────────────


class PolicyOverride:
    """Temporary policy overrides with automatic expiry.

    Overrides are keyed by policy name.  Each override carries an
    expiration timestamp; :meth:`get` returns ``None`` for expired
    overrides and :meth:`active_overrides` excludes them.
    """

    def __init__(self) -> None:
        self._overrides: dict[str, Override] = {}

    def set(
        self,
        policy: str,
        value: Any,
        *,
        actor: str,
        reason: str,
        expires_at: str,
    ) -> Override:
        """Create or replace an override for *policy*."""
        now = datetime.now(timezone.utc).isoformat()
        override = Override(
            policy=policy,
            value=value,
            actor=actor,
            reason=reason,
            expires_at=expires_at,
            created_at=now,
        )
        self._overrides[policy] = override
        return override

    def get(self, policy: str) -> Any | None:
        """Return the override value if active, else ``None``."""
        override = self._overrides.get(policy)
        if override is None:
            return None
        now = datetime.now(timezone.utc)
        if datetime.fromisoformat(override.expires_at) <= now:
            return None
        return override.value

    def revoke(self, policy: str) -> bool:
        """Remove an override.  Returns ``True`` if it existed."""
        return self._overrides.pop(policy, None) is not None

    def active_overrides(self) -> list[Override]:
        """Return all non-expired overrides."""
        now = datetime.now(timezone.utc)
        return [
            o
            for o in self._overrides.values()
            if datetime.fromisoformat(o.expires_at) > now
        ]
