"""Tests for unified MCP server (#722)."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from loom_ai.mcp_server import (
    _TOOLS,
    _dispatch,
    _handle,
    _negotiate_version,
    _read_message,
    _write_message,
)


class TestNegotiateVersion:
    def test_echoes_supported_version(self):
        assert _negotiate_version("2024-11-05") == "2024-11-05"
        assert _negotiate_version("2025-03-26") == "2025-03-26"

    def test_falls_back_to_latest(self):
        assert _negotiate_version("1999-01-01") == "2025-03-26"
        assert _negotiate_version(None) == "2025-03-26"


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        for tool in _TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_expected_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert "loom_chat" in names
        assert "loom_search" in names
        assert "loom_store" in names
        assert "loom_consensus" in names
        assert "loom_synthesize" in names
        assert "loom_queue_enqueue" in names
        assert "loom_queue_status" in names
        assert "loom_secret_list" in names
        assert "loom_secret_get" in names
        assert "loom_graph_add_node" in names
        assert "loom_graph_neighbors" in names
        assert "loom_router_select" in names
        assert "loom_router_stats" in names
        assert "loom_health" in names
        assert "loom_list_models" in names


class TestHandle:
    def test_returns_error_for_unknown_tool(self):
        result = _handle("nonexistent_tool", {})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    @patch("loom_ai.mcp_server._api")
    def test_dispatches_health(self, mock_api):
        mock_api.return_value = {"status": "healthy"}
        result = _handle("loom_health", {})
        assert "isError" not in result
        text = result["content"][0]["text"]
        assert "healthy" in text

    @patch("loom_ai.mcp_server._api")
    def test_dispatches_search(self, mock_api):
        mock_api.return_value = {"results": [], "query": "test"}
        result = _handle("loom_search", {"query": "test"})
        assert "isError" not in result

    @patch("loom_ai.mcp_server._api")
    def test_dispatches_chat(self, mock_api):
        mock_api.return_value = {"content": "hello", "model": "m1"}
        result = _handle(
            "loom_chat",
            {
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert "isError" not in result

    @patch("loom_ai.mcp_server._api")
    def test_dispatches_store(self, mock_api):
        mock_api.return_value = {"id": "doc-1", "stored": True}
        result = _handle(
            "loom_store",
            {
                "title": "Test",
                "content": "body",
            },
        )
        assert "isError" not in result


class TestDispatch:
    @patch("loom_ai.mcp_server._api")
    def test_list_models(self, mock_api):
        mock_api.return_value = {"models": ["a", "b"], "count": 2}
        result = _dispatch("loom_list_models", {})
        assert result["count"] == 2

    @patch("loom_ai.mcp_server._api")
    def test_queue_status(self, mock_api):
        mock_api.return_value = {"pending": 5}
        result = _dispatch(
            "loom_queue_status",
            {
                "queue_name": "test-q",
            },
        )
        assert result["pending"] == 5

    @patch("loom_ai.mcp_server._api")
    def test_queue_enqueue(self, mock_api):
        mock_api.return_value = {"enqueued": 1}
        result = _dispatch(
            "loom_queue_enqueue",
            {
                "queue_name": "q",
                "payload": {"x": 1},
            },
        )
        assert result["enqueued"] == 1

    @patch("loom_ai.mcp_server._api")
    def test_graph_add_node(self, mock_api):
        mock_api.return_value = {"id": "node-1"}
        result = _dispatch(
            "loom_graph_add_node",
            {
                "label": "test",
            },
        )
        assert result["id"] == "node-1"

    @patch("loom_ai.mcp_server._api")
    def test_router_select(self, mock_api):
        mock_api.return_value = {"model": "gpt-4o", "task_type": "code"}
        result = _dispatch(
            "loom_router_select",
            {
                "task_type": "code",
            },
        )
        assert result["model"] == "gpt-4o"


class TestMessageFraming:
    def test_read_message(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "ping"})
        raw = f"Content-Length: {len(body)}\r\n\r\n{body}"
        with patch("sys.stdin", StringIO(raw)):
            msg = _read_message()
        assert msg["method"] == "ping"

    def test_read_returns_none_on_empty(self):
        with patch("sys.stdin", StringIO("")):
            msg = _read_message()
        assert msg is None

    def test_write_message(self):
        buf = StringIO()
        with patch("sys.stdout", buf):
            _write_message({"jsonrpc": "2.0", "id": 1, "result": {}})
        output = buf.getvalue()
        assert "Content-Length:" in output
        assert '"jsonrpc"' in output
