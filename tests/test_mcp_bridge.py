"""MCP bridge protocol validation and version negotiation."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from loom_ai.clients.claude import mcp_bridge as bridge


def test_negotiate_supported_versions():
    assert bridge._negotiate_protocol({"protocolVersion": "2024-11-05"}) == "2024-11-05"
    assert bridge._negotiate_protocol({"protocolVersion": "2025-03-26"}) == "2025-03-26"
    assert bridge._negotiate_protocol({}) == bridge._DEFAULT_PROTOCOL_VERSION


def test_negotiate_unsupported():
    with pytest.raises(ValueError, match="unsupported"):
        bridge._negotiate_protocol({"protocolVersion": "1999-01-01"})


def test_clamp_limit():
    assert bridge._clamp_limit(10) == 10
    assert bridge._clamp_limit(9999) == bridge._MAX_SEARCH_LIMIT
    with pytest.raises(ValueError):
        bridge._clamp_limit(0)
    with pytest.raises(ValueError):
        bridge._clamp_limit("x")


def test_require_str():
    assert bridge._require_str({"q": "hi"}, "q") == "hi"
    with pytest.raises(ValueError):
        bridge._require_str({}, "q")


def test_handle_tool_unknown():
    with pytest.raises(ValueError, match="unknown tool"):
        bridge._handle_tool_call("nope", {})


def test_handle_tool_missing_args():
    with pytest.raises(ValueError, match="query"):
        bridge._handle_tool_call("loom_search", {})


def test_handle_tool_invalid_models():
    with pytest.raises(ValueError, match="models"):
        bridge._handle_tool_call("loom_consensus", {"prompt": "x", "models": []})


def test_parse_error_on_bad_json():
    body = b"{not}"
    bad = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    buf = io.BytesIO(bad)

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        with pytest.raises(bridge._ParseError):
            bridge._read_message()


def test_framing_invalid_length():
    bad = b"Content-Length: abc\r\n\r\n"
    buf = io.BytesIO(bad)

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        with pytest.raises(bridge._FramingError):
            bridge._read_message()


def test_framing_truncated_body():
    bad = b"Content-Length: 100\r\n\r\nshort"
    buf = io.BytesIO(bad)

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        with pytest.raises(bridge._FramingError, match="truncated"):
            bridge._read_message()


def test_framing_oversized_content_length():
    huge = bridge._MAX_CONTENT_LENGTH + 1
    bad = f"Content-Length: {huge}\r\n\r\n".encode()
    buf = io.BytesIO(bad)

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        with pytest.raises(bridge._FramingError, match="out of range"):
            bridge._read_message()


def test_read_clean_eof():
    buf = io.BytesIO(b"")

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        assert bridge._read_message() is None


def test_dispatch_unknown_method():
    written = []

    def capture(msg):
        written.append(msg)

    with patch.object(bridge, "_write_message", side_effect=capture):
        assert bridge._dispatch({"jsonrpc": "2.0", "id": 1, "method": "nope"}) is True
    assert written[0]["error"]["code"] == bridge._METHOD_NOT_FOUND


def test_dispatch_tools_call_invalid_args():
    written = []

    def capture(msg):
        written.append(msg)

    with patch.object(bridge, "_write_message", side_effect=capture):
        assert (
            bridge._dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "loom_search", "arguments": {}},
                }
            )
            is True
        )
    assert written[0]["error"]["code"] == bridge._INVALID_PARAMS


def test_framing_missing_content_length():
    """Header block without Content-Length is a framing error, not a retry."""
    bad = b"X-Unused: 1\r\n\r\n"
    buf = io.BytesIO(bad)

    class _Fake:
        buffer = buf

    with patch.object(bridge.sys, "stdin", _Fake()):
        with pytest.raises(bridge._FramingError, match="missing Content-Length"):
            bridge._read_message()
