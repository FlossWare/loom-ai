"""Tests for hardened REST secrets endpoints (issue #242).

Verifies that:
- Secret values are never exposed by metadata/list endpoints.
- ``POST /secrets/{name}/reveal`` is the sole path returning plaintext values.
- ``X-Secret-Access-Reason`` header is required to reveal a secret.
- All reveal requests are audit-logged.
- Error messages do not leak secret names or values.
- Auth is enforced on all secrets endpoints when ``LOOM_API_KEY`` is set.
"""

from __future__ import annotations

import logging

import pytest

# Guard: skip the whole module when fastapi is not installed (e.g. backend
# matrix jobs that only install postgresql/redis/etc extras without server).
pytest.importorskip("fastapi", reason="fastapi not installed (server extra)")

from fastapi.testclient import TestClient  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUTH_HEADER = {"Authorization": "Bearer test-key"}


def _make_app(monkeypatch, *, api_key: str | None = None, secrets: dict | None = None):
    """Build a FastAPI app with in-memory secrets backend.

    *secrets* is a dict of name->value pairs pre-loaded into the backend.
    """
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    if api_key is not None:
        monkeypatch.setenv("LOOM_API_KEY", api_key)

    import asyncio

    from loom_ai.backends.env_secrets import EnvSecretsBackend
    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    secrets_backend = EnvSecretsBackend(overrides=secrets or {})
    cfg = asyncio.run(LoomConfig.from_env())
    # Swap in our pre-loaded secrets backend
    cfg = LoomConfig(
        storage=cfg.storage,
        queue=cfg.queue,
        secrets=secrets_backend,
        embedding=cfg.embedding,
        search=cfg.search,
    )
    return create_app(cfg)


def _client(monkeypatch, **kwargs) -> TestClient:
    return TestClient(_make_app(monkeypatch, **kwargs))


# ---------------------------------------------------------------------------
# GET /secrets/ -- list names only
# ---------------------------------------------------------------------------


def test_list_secrets_returns_names_only(monkeypatch):
    """GET /secrets/ returns secret names without any values."""
    client = _client(monkeypatch, secrets={"DB_PASS": "hunter2"})
    resp = client.get("/secrets/")
    assert resp.status_code == 200
    body = resp.json()
    assert "DB_PASS" in body["secrets"]
    # Must not contain values anywhere in the response
    assert "hunter2" not in resp.text


# ---------------------------------------------------------------------------
# GET /secrets/{name} -- metadata only (exists check)
# ---------------------------------------------------------------------------


def test_get_secret_metadata_exists(monkeypatch):
    """GET /secrets/{name} returns exists=True without the value."""
    client = _client(monkeypatch, secrets={"MY_SECRET": "s3cret"})
    resp = client.get("/secrets/MY_SECRET")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "MY_SECRET"
    assert body["exists"] is True
    # Value must not be in the response
    assert "value" not in body
    assert "s3cret" not in resp.text


def test_get_secret_metadata_not_found(monkeypatch):
    """GET /secrets/{name} returns 404 when the secret does not exist."""
    client = _client(monkeypatch, secrets={})
    resp = client.get("/secrets/DOES_NOT_EXIST")
    assert resp.status_code == 404
    # Error must not echo the secret name back
    assert "DOES_NOT_EXIST" not in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# POST /secrets/{name}/reveal -- explicit retrieval
# ---------------------------------------------------------------------------


def test_reveal_returns_value(monkeypatch):
    """POST /secrets/{name}/reveal with reason header returns the value."""
    client = _client(monkeypatch, secrets={"API_KEY": "sk-abc123"})
    resp = client.post(
        "/secrets/API_KEY/reveal",
        headers={"X-Secret-Access-Reason": "deploy script"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "API_KEY"
    assert body["value"] == "sk-abc123"


def test_reveal_missing_reason_header(monkeypatch):
    """POST /secrets/{name}/reveal without reason header returns 400."""
    client = _client(monkeypatch, secrets={"API_KEY": "sk-abc123"})
    resp = client.post("/secrets/API_KEY/reveal")
    assert resp.status_code == 400
    assert "X-Secret-Access-Reason" in resp.json()["detail"]
    # Must not leak the value
    assert "sk-abc123" not in resp.text


def test_reveal_empty_reason_header(monkeypatch):
    """An empty X-Secret-Access-Reason is rejected."""
    client = _client(monkeypatch, secrets={"API_KEY": "sk-abc123"})
    resp = client.post(
        "/secrets/API_KEY/reveal",
        headers={"X-Secret-Access-Reason": ""},
    )
    assert resp.status_code == 400


def test_reveal_not_found(monkeypatch):
    """POST /secrets/{name}/reveal returns 404 for missing secrets."""
    client = _client(monkeypatch, secrets={})
    resp = client.post(
        "/secrets/GHOST/reveal",
        headers={"X-Secret-Access-Reason": "testing"},
    )
    assert resp.status_code == 404
    # Error must not echo the secret name
    assert "GHOST" not in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def test_reveal_logs_access(monkeypatch, caplog):
    """Successful reveal is audit-logged at INFO level."""
    client = _client(monkeypatch, secrets={"TOKEN": "tok-xyz"})
    with caplog.at_level(logging.INFO, logger="loom_ai.server"):
        client.post(
            "/secrets/TOKEN/reveal",
            headers={"X-Secret-Access-Reason": "CI pipeline"},
        )
    assert any(
        "secrets.reveal GRANTED" in r.message and "TOKEN" in r.message
        for r in caplog.records
    )
    # The value must not appear in log messages
    assert not any("tok-xyz" in r.message for r in caplog.records)


def test_reveal_logs_denied_missing_header(monkeypatch, caplog):
    """Reveal denied (missing header) is audit-logged at WARNING."""
    client = _client(monkeypatch, secrets={"TOKEN": "tok-xyz"})
    with caplog.at_level(logging.WARNING, logger="loom_ai.server"):
        client.post("/secrets/TOKEN/reveal")
    assert any(
        "secrets.reveal DENIED" in r.message and "missing_header" in r.message
        for r in caplog.records
    )


def test_reveal_logs_not_found(monkeypatch, caplog):
    """Reveal of non-existent secret is audit-logged at INFO."""
    client = _client(monkeypatch, secrets={})
    with caplog.at_level(logging.INFO, logger="loom_ai.server"):
        client.post(
            "/secrets/NOPE/reveal",
            headers={"X-Secret-Access-Reason": "lookup"},
        )
    assert any("secrets.reveal NOT_FOUND" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Auth enforcement -- all secrets endpoints require auth when key is set
# ---------------------------------------------------------------------------


def test_list_requires_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.get("/secrets/")
    assert resp.status_code in (401, 403)


def test_metadata_requires_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.get("/secrets/A")
    assert resp.status_code in (401, 403)


def test_reveal_requires_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.post(
        "/secrets/A/reveal",
        headers={"X-Secret-Access-Reason": "test"},
    )
    assert resp.status_code in (401, 403)


def test_list_with_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.get("/secrets/", headers=_AUTH_HEADER)
    assert resp.status_code == 200


def test_metadata_with_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.get("/secrets/A", headers=_AUTH_HEADER)
    assert resp.status_code == 200


def test_reveal_with_auth(monkeypatch):
    client = _client(monkeypatch, api_key="test-key", secrets={"A": "1"})
    resp = client.post(
        "/secrets/A/reveal",
        headers={**_AUTH_HEADER, "X-Secret-Access-Reason": "authorized"},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "1"


# ---------------------------------------------------------------------------
# No-auth mode -- all endpoints accessible without a key
# ---------------------------------------------------------------------------


def test_list_no_auth_mode(monkeypatch):
    client = _client(monkeypatch, secrets={"X": "val"})
    assert client.get("/secrets/").status_code == 200


def test_metadata_no_auth_mode(monkeypatch):
    client = _client(monkeypatch, secrets={"X": "val"})
    assert client.get("/secrets/X").status_code == 200


def test_reveal_no_auth_mode(monkeypatch):
    client = _client(monkeypatch, secrets={"X": "val"})
    resp = client.post(
        "/secrets/X/reveal",
        headers={"X-Secret-Access-Reason": "no-auth test"},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "val"


# ---------------------------------------------------------------------------
# Error sanitization -- no secret material in error responses
# ---------------------------------------------------------------------------


def test_404_does_not_echo_secret_name(monkeypatch):
    """A generic 'not found' message prevents name enumeration clues."""
    client = _client(monkeypatch, secrets={})
    resp = client.get("/secrets/VERY_SPECIFIC_NAME_12345")
    assert resp.status_code == 404
    assert "VERY_SPECIFIC_NAME_12345" not in resp.text
