"""Security: API key transport and non-loopback bind guards."""

from __future__ import annotations

import pytest

from loom_ai.clients.client import ClientConfig
from loom_ai.clients.transport_security import validate_api_key_transport
from loom_ai.security_bind import is_loopback_host, require_api_key_for_non_loopback


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("example.com", False),
    ],
)
def test_is_loopback_host(host, expected):
    assert is_loopback_host(host) is expected


def test_require_api_key_loopback_ok():
    require_api_key_for_non_loopback("127.0.0.1", None)
    require_api_key_for_non_loopback("localhost", None)


def test_require_api_key_non_loopback_fails():
    with pytest.raises(SystemExit, match="LOOM_API_KEY") as exc_info:
        require_api_key_for_non_loopback("0.0.0.0", None)
    assert "LOOM_API_KEY" in str(exc_info.value)


def test_require_api_key_non_loopback_with_key_ok():
    require_api_key_for_non_loopback("0.0.0.0", "secret")


def test_transport_https_with_key_ok():
    validate_api_key_transport("https://api.example.com", "k")


def test_transport_http_loopback_with_key_ok():
    validate_api_key_transport("http://127.0.0.1:5000", "k")


def test_transport_http_remote_with_key_fails():
    with pytest.raises(ValueError, match="plaintext HTTP") as exc_info:
        validate_api_key_transport("http://api.example.com", "k")
    assert "plaintext HTTP" in str(exc_info.value)


def test_transport_http_remote_insecure_override():
    validate_api_key_transport("http://api.example.com", "k", allow_insecure_http=True)


def test_transport_http_remote_without_key_ok():
    validate_api_key_transport("http://api.example.com", "")


def test_client_config_defaults_loopback():
    cfg = ClientConfig()
    assert "127.0.0.1" in cfg.base_url or "localhost" in cfg.base_url
