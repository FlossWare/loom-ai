"""Conformance tests for SecretsBackend implementations.

Any backend that satisfies the SecretsBackend protocol should pass all
tests in this module.  Override the ``secrets_backend`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations


async def test_get_existing_secret(secrets_backend):
    """Retrieving a pre-loaded secret returns its value."""
    value = await secrets_backend.get("API_KEY")
    assert value == "test-key-123"


async def test_get_missing_secret_returns_none(secrets_backend):
    """Requesting a non-existent secret returns None."""
    result = await secrets_backend.get("NO_SUCH_SECRET_XYZ_999")
    assert result is None


async def test_list_secret_names(secrets_backend):
    """list_names includes the pre-loaded key."""
    names = await secrets_backend.list_names()
    assert "API_KEY" in names


async def test_set_and_retrieve(secrets_backend):
    """Setting a new secret and reading it back returns the value."""
    ok = await secrets_backend.set("NEW_KEY", "new-value")
    assert ok is True

    value = await secrets_backend.get("NEW_KEY")
    assert value == "new-value"


async def test_set_overwrites_existing(secrets_backend):
    """Setting an existing secret overwrites its value."""
    await secrets_backend.set("API_KEY", "updated-value")
    value = await secrets_backend.get("API_KEY")
    assert value == "updated-value"


async def test_delete_secret(secrets_backend):
    """Deleting a secret removes it from the in-memory store."""
    await secrets_backend.set("TEMP_KEY", "temporary")
    deleted = await secrets_backend.delete("TEMP_KEY")
    assert deleted is True


async def test_delete_missing_returns_false(secrets_backend):
    """Deleting a non-existent secret returns False."""
    result = await secrets_backend.delete("NEVER_EXISTED")
    assert result is False
