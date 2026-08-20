"""Security: API key transport and non-loopback bind guards."""

from __future__ import annotations

import pytest

from loom_ai.clients.client import ClientConfig, LoomClient
from loom_ai.server import _is_loopback_host, _require_api_key_for_non_loopback


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
    assert _is_loopback_host(host) is expected


def test_require_api_key_loopback_ok():
    _require_api_key_for_non_loopback("127.0.0.1", None)
    _require_api_key_for_non_loopback("localhost", None)


def test_require_api_key_non_loopback_fails():
    with pytest.raises(SystemExit, match="LOOM_API_KEY"):
        _require_api_key_for_non_loopback("0.0.0.0", None)


def test_require_api_key_non_loopback_with_key_ok():
    _require_api_key_for_non_loopback("0.0.0.0", "secret")


def test_client_https_with_key_ok():
    ClientConfig(base_url="https://api.example.com", api_key="k").validate_transport()


def test_client_http_loopback_with_key_ok():
    ClientConfig(base_url="http://127.0.0.1:5000", api_key="k").validate_transport()


def test_client_http_remote_with_key_fails():
    with pytest.raises(ValueError, match="plaintext HTTP"):
        ClientConfig(
            base_url="http://api.example.com", api_key="k"
        ).validate_transport()


def test_client_http_remote_insecure_override():
    ClientConfig(
        base_url="http://api.example.com",
        api_key="k",
        allow_insecure_http=True,
    ).validate_transport()


def test_client_http_remote_without_key_ok():
    ClientConfig(base_url="http://api.example.com", api_key="").validate_transport()


def test_loom_client_init_rejects_insecure():
    with pytest.raises(ValueError, match="plaintext HTTP"):
        LoomClient(ClientConfig(base_url="http://remote.example", api_key="secret"))
