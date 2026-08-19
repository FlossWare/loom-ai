"""Tests for MCP bridge protocol negotiation and input validation (#441, #442)."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from loom_ai.clients.claude.mcp_bridge import (
    _LATEST_VERSION,
    _MAX_MESSAGE_SIZE,
    _PARSE_ERROR,
    _SUPPORTED_VERSIONS,
    _dispatch,
    _handle_tool_call,
    _read_message,
    _ToolError,
    _validate_arguments,
)

# ── Protocol negotiation (#441) ─────────────────────────────────────


def _capture_writes():
    """Return a list that collects dicts written via _write_message."""
    sent: list[dict] = []

    def fake_write(data: dict) -> None:
        sent.append(data)

    return sent, fake_write


class TestProtocolNegotiation:
    def test_supported_version_echoed(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            _dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            )
        result = sent[0]["result"]
        assert result["protocolVersion"] == "2024-11-05"

    def test_latest_supported_version_echoed(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            _dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": _LATEST_VERSION},
                }
            )
        result = sent[0]["result"]
        assert result["protocolVersion"] == _LATEST_VERSION

    def test_unsupported_version_falls_back_to_latest(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            _dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {"protocolVersion": "2099-01-01"},
                }
            )
        result = sent[0]["result"]
        assert result["protocolVersion"] == _LATEST_VERSION

    def test_missing_version_falls_back_to_latest(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            _dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "initialize",
                    "params": {},
                }
            )
        result = sent[0]["result"]
        assert result["protocolVersion"] == _LATEST_VERSION

    def test_supported_versions_list_not_empty(self):
        assert len(_SUPPORTED_VERSIONS) >= 2
        assert _LATEST_VERSION in _SUPPORTED_VERSIONS


# ── Input validation (#442) ─────────────────────────────────────────


def _fake_stdin(raw: bytes):
    """Create a mock sys.stdin with a working .buffer attribute."""
    buf = io.BufferedReader(io.BytesIO(raw))
    mock_stdin = type("FakeStdin", (), {"buffer": buf})()
    return mock_stdin


class TestReadMessageValidation:
    def test_valid_message(self):
        body = json.dumps({"method": "tools/list", "id": 1}).encode()
        raw = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        sent, writer = _capture_writes()
        with (
            patch("sys.stdin", _fake_stdin(raw)),
            patch("loom_ai.clients.claude.mcp_bridge._write_message", writer),
        ):
            msg = _read_message()
        assert msg == {"method": "tools/list", "id": 1}
        assert len(sent) == 0

    def test_invalid_json_returns_parse_error(self):
        bad_body = b"not json at all"
        raw = f"Content-Length: {len(bad_body)}\r\n\r\n".encode() + bad_body
        sent, writer = _capture_writes()
        with (
            patch("sys.stdin", _fake_stdin(raw)),
            patch("loom_ai.clients.claude.mcp_bridge._write_message", writer),
        ):
            msg = _read_message()
        assert msg is _PARSE_ERROR
        assert sent[0]["error"]["code"] == -32700

    def test_negative_content_length_returns_parse_error(self):
        raw = b"Content-Length: -5\r\n\r\n"
        sent, writer = _capture_writes()
        with (
            patch("sys.stdin", _fake_stdin(raw)),
            patch("loom_ai.clients.claude.mcp_bridge._write_message", writer),
        ):
            msg = _read_message()
        assert msg is _PARSE_ERROR
        assert sent[0]["error"]["code"] == -32700

    def test_non_integer_content_length_returns_parse_error(self):
        raw = b"Content-Length: abc\r\n\r\n"
        sent, writer = _capture_writes()
        with (
            patch("sys.stdin", _fake_stdin(raw)),
            patch("loom_ai.clients.claude.mcp_bridge._write_message", writer),
        ):
            msg = _read_message()
        assert msg is _PARSE_ERROR
        assert sent[0]["error"]["code"] == -32700

    def test_oversized_content_length_returns_parse_error(self):
        huge_length = _MAX_MESSAGE_SIZE + 1
        raw = f"Content-Length: {huge_length}\r\n\r\n".encode()
        sent, writer = _capture_writes()
        with (
            patch("sys.stdin", _fake_stdin(raw)),
            patch("loom_ai.clients.claude.mcp_bridge._write_message", writer),
        ):
            msg = _read_message()
        assert msg is _PARSE_ERROR
        assert sent[0]["error"]["code"] == -32700

    def test_eof_returns_none(self):
        with patch("sys.stdin", _fake_stdin(b"")):
            msg = _read_message()
        assert msg is None


class TestDispatchValidation:
    def test_missing_method_returns_invalid_request(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            result = _dispatch({"jsonrpc": "2.0", "id": 5})
        assert result is True
        assert sent[0]["error"]["code"] == -32600

    def test_unknown_method_returns_method_not_found(self):
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            _dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "nonexistent/method",
                }
            )
        assert sent[0]["error"]["code"] == -32601

    def test_notification_without_method_ignored(self):
        """A message with no id and no method should not crash."""
        sent, writer = _capture_writes()
        with patch("loom_ai.clients.claude.mcp_bridge._write_message", writer):
            result = _dispatch({"jsonrpc": "2.0"})
        assert result is True
        assert sent[0]["error"]["code"] == -32600


class TestToolArgumentValidation:
    def test_missing_required_argument(self):
        with pytest.raises(_ToolError, match="Missing required argument"):
            _validate_arguments("loom_search", {})

    def test_wrong_type_string(self):
        with pytest.raises(_ToolError, match="must be string"):
            _validate_arguments("loom_search", {"query": 123})

    def test_wrong_type_array(self):
        with pytest.raises(_ToolError, match="must be array"):
            _validate_arguments(
                "loom_consensus",
                {
                    "prompt": "test",
                    "models": "not-a-list",
                },
            )

    def test_unknown_tool(self):
        with pytest.raises(_ToolError, match="Unknown tool"):
            _validate_arguments("nonexistent_tool", {})

    def test_non_dict_arguments(self):
        with pytest.raises(_ToolError, match="key-value object"):
            _validate_arguments("loom_search", "not a dict")

    def test_optional_arg_wrong_type_rejected(self):
        with pytest.raises(_ToolError, match="must be integer"):
            _validate_arguments("loom_search", {"query": "hello", "limit": "ten"})

    def test_optional_arg_correct_type_passes(self):
        _validate_arguments("loom_search", {"query": "hello", "limit": 5})

    def test_valid_arguments_pass(self):
        _validate_arguments("loom_search", {"query": "hello"})
        _validate_arguments(
            "loom_store",
            {
                "title": "t",
                "content": "c",
            },
        )
        _validate_arguments(
            "loom_consensus",
            {
                "prompt": "p",
                "models": ["m1"],
            },
        )


class TestHandleToolCallErrors:
    def test_unknown_tool_returns_is_error(self):
        result = _handle_tool_call("nonexistent", {})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_missing_arg_returns_is_error(self):
        result = _handle_tool_call("loom_search", {})
        assert result["isError"] is True
        assert "Missing required" in result["content"][0]["text"]

    def test_transport_error_returns_is_error(self):
        with patch(
            "loom_ai.clients.claude.mcp_bridge._api_request",
            side_effect=_ToolError("Connection failed: refused"),
        ):
            result = _handle_tool_call("loom_search", {"query": "test"})
        assert result["isError"] is True
        assert "Connection failed" in result["content"][0]["text"]

    def test_successful_call_no_is_error(self):
        with patch(
            "loom_ai.clients.claude.mcp_bridge._api_request",
            return_value={"results": []},
        ):
            result = _handle_tool_call("loom_search", {"query": "test"})
        assert "isError" not in result
        assert json.loads(result["content"][0]["text"]) == {"results": []}
