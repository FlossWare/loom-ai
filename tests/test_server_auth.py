"""Tests for server authentication middleware."""

from fastapi.testclient import TestClient


def _make_app(monkeypatch, api_key=None):
    """Create a test app with optional auth."""
    monkeypatch.delenv("LOOM_API_KEY", raising=False)
    if api_key is not None:
        monkeypatch.setenv("LOOM_API_KEY", api_key)
    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    return create_app(LoomConfig.from_env())


def test_health_no_auth_required(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_no_api_key_allows_all(monkeypatch):
    app = _make_app(monkeypatch)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/knowledge/stats").status_code == 200


def test_valid_key_allows_access(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get(
        "/knowledge/stats", headers={"Authorization": "Bearer test-secret"}
    )
    assert resp.status_code == 200


def test_invalid_key_returns_401(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/knowledge/stats", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_missing_auth_header_returns_error(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/knowledge/stats")
    assert resp.status_code in (401, 403)


def test_secrets_requires_auth(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/secrets/")
    assert resp.status_code in (401, 403)


def test_secrets_accessible_with_valid_key(monkeypatch):
    app = _make_app(monkeypatch, api_key="test-secret")
    client = TestClient(app)
    resp = client.get("/secrets/", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
