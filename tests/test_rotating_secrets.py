"""Tests for RotatingSecretsBackend (issue #292).

Verifies:
- Fallback chain (primary fails, secondary succeeds)
- Key rotation (old key replaced, new key returned)
- TTL expiry (expired keys return None)
- Validation callback (invalid values are skipped)
- list_names aggregation across backends and rotated keys
- delete clears rotation overrides and TTL
"""

from __future__ import annotations

import pytest

from loom_ai.backends.env_secrets import EnvSecretsBackend
from loom_ai.backends.rotating_secrets import RotatingSecretsBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FailingSecretsBackend:
    """Backend that raises on every operation."""

    async def get(self, name: str) -> str | None:
        raise RuntimeError("backend unavailable")

    async def set(self, name: str, value: str) -> bool:
        raise RuntimeError("backend unavailable")

    async def list_names(self) -> list[str]:
        raise RuntimeError("backend unavailable")

    async def delete(self, name: str) -> bool:
        raise RuntimeError("backend unavailable")


def _env_backend(**secrets: str) -> EnvSecretsBackend:
    return EnvSecretsBackend(overrides=secrets)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_requires_at_least_one_backend():
    with pytest.raises(ValueError, match="at least one backend"):
        RotatingSecretsBackend(backends=[])


# ---------------------------------------------------------------------------
# Single backend (baseline)
# ---------------------------------------------------------------------------


async def test_get_from_single_backend():
    backend = RotatingSecretsBackend(backends=[_env_backend(API_KEY="sk-abc")])
    assert await backend.get("API_KEY") == "sk-abc"


async def test_get_missing_key():
    backend = RotatingSecretsBackend(backends=[_env_backend()])
    assert await backend.get("MISSING") is None


async def test_set_delegates_to_primary():
    primary = _env_backend()
    backend = RotatingSecretsBackend(backends=[primary])
    assert await backend.set("NEW_KEY", "val") is True
    assert await primary.get("NEW_KEY") == "val"


async def test_delete_delegates_to_primary():
    primary = _env_backend(TEMP="x")
    backend = RotatingSecretsBackend(backends=[primary])
    assert await backend.delete("TEMP") is True
    assert await primary.get("TEMP") is None


async def test_list_names_from_single_backend():
    backend = RotatingSecretsBackend(backends=[_env_backend(A="1", B="2")])
    names = await backend.list_names()
    assert "A" in names
    assert "B" in names


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


async def test_fallback_primary_fails_secondary_succeeds():
    failing = FailingSecretsBackend()
    secondary = _env_backend(DB_PASS="hunter2")
    backend = RotatingSecretsBackend(backends=[failing, secondary])
    assert await backend.get("DB_PASS") == "hunter2"


async def test_fallback_primary_returns_none_secondary_has_value():
    primary = _env_backend()
    secondary = _env_backend(FALLBACK_KEY="found")
    backend = RotatingSecretsBackend(backends=[primary, secondary])
    assert await backend.get("FALLBACK_KEY") == "found"


async def test_fallback_all_miss():
    primary = _env_backend()
    secondary = _env_backend()
    backend = RotatingSecretsBackend(backends=[primary, secondary])
    assert await backend.get("NOWHERE") is None


async def test_list_names_merges_all_backends():
    primary = _env_backend(A="1")
    secondary = _env_backend(B="2")
    backend = RotatingSecretsBackend(backends=[primary, secondary])
    names = await backend.list_names()
    assert "A" in names
    assert "B" in names


async def test_list_names_with_failing_backend():
    failing = FailingSecretsBackend()
    secondary = _env_backend(X="1")
    backend = RotatingSecretsBackend(backends=[failing, secondary])
    names = await backend.list_names()
    assert "X" in names


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------


async def test_rotation_returns_new_value():
    primary = _env_backend(API_KEY="old-key")
    backend = RotatingSecretsBackend(backends=[primary])
    backend.rotate("API_KEY", "new-key")
    assert await backend.get("API_KEY") == "new-key"


async def test_rotation_overrides_all_backends():
    primary = _env_backend(TOKEN="primary-val")
    secondary = _env_backend(TOKEN="secondary-val")
    backend = RotatingSecretsBackend(backends=[primary, secondary])
    backend.rotate("TOKEN", "rotated-val")
    assert await backend.get("TOKEN") == "rotated-val"


async def test_rotation_for_nonexistent_key():
    backend = RotatingSecretsBackend(backends=[_env_backend()])
    backend.rotate("BRAND_NEW", "fresh-value")
    assert await backend.get("BRAND_NEW") == "fresh-value"


async def test_rotated_key_appears_in_list_names():
    backend = RotatingSecretsBackend(backends=[_env_backend()])
    backend.rotate("ROTATED", "val")
    assert "ROTATED" in await backend.list_names()


async def test_delete_clears_rotation():
    primary = _env_backend()
    backend = RotatingSecretsBackend(backends=[primary])
    backend.rotate("KEY", "rotated")
    assert await backend.get("KEY") == "rotated"
    await backend.delete("KEY")
    assert await backend.get("KEY") is None


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


async def test_ttl_not_expired():
    primary = _env_backend(SECRET="val")
    backend = RotatingSecretsBackend(backends=[primary])
    backend.set_ttl("SECRET", 3600)
    assert await backend.get("SECRET") == "val"


async def test_ttl_expired(monkeypatch):
    primary = _env_backend(SECRET="val")
    backend = RotatingSecretsBackend(backends=[primary])
    backend.set_ttl("SECRET", 10)

    import time

    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 11)

    assert await backend.get("SECRET") is None


async def test_ttl_expired_rotated_key(monkeypatch):
    backend = RotatingSecretsBackend(backends=[_env_backend()])
    backend.rotate("KEY", "rotated-val")
    backend.set_ttl("KEY", 5)

    import time

    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 6)

    assert await backend.get("KEY") is None


async def test_delete_clears_ttl():
    primary = _env_backend(SECRET="val")
    backend = RotatingSecretsBackend(backends=[primary])
    backend.set_ttl("SECRET", 3600)
    await backend.delete("SECRET")
    assert "SECRET" not in backend._ttls


# ---------------------------------------------------------------------------
# Validation callback
# ---------------------------------------------------------------------------


async def test_validator_accepts():
    def accept_all(name: str, value: str) -> bool:
        return True

    backend = RotatingSecretsBackend(
        backends=[_env_backend(KEY="valid")],
        validator=accept_all,
    )
    assert await backend.get("KEY") == "valid"


async def test_validator_rejects():
    def reject_all(name: str, value: str) -> bool:
        return False

    backend = RotatingSecretsBackend(
        backends=[_env_backend(KEY="invalid")],
        validator=reject_all,
    )
    assert await backend.get("KEY") is None


async def test_validator_rejects_primary_accepts_secondary():
    """Validator rejects value from primary; fallback secondary passes."""
    primary = _env_backend(TOKEN="bad-format")
    secondary = _env_backend(TOKEN="sk-valid-123")

    def require_prefix(name: str, value: str) -> bool:
        return value.startswith("sk-")

    backend = RotatingSecretsBackend(
        backends=[primary, secondary],
        validator=require_prefix,
    )
    assert await backend.get("TOKEN") == "sk-valid-123"


async def test_validator_on_rotated_key():
    def reject_all(name: str, value: str) -> bool:
        return False

    backend = RotatingSecretsBackend(
        backends=[_env_backend()],
        validator=reject_all,
    )
    backend.rotate("KEY", "rotated")
    assert await backend.get("KEY") is None


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


async def test_satisfies_secrets_backend_protocol():
    from loom_ai.protocols import SecretsBackend

    backend = RotatingSecretsBackend(backends=[_env_backend()])
    assert isinstance(backend, SecretsBackend)
