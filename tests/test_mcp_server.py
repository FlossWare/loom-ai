"""Tests for unified MCP server (#722)."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from loom_ai.mcp_server import (
    _DISPATCH_TABLE,
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
        assert "loom_graph_add_entity" in names
        assert "loom_graph_relationships" in names
        assert "loom_router_select" in names
        assert "loom_router_stats" in names
        assert "loom_health" in names
        assert "loom_list_models" in names
        assert "loom_resolve_issue_async" in names
        assert "loom_resolve_issue_status" in names


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
    def test_graph_add_entity(self, mock_api):
        mock_api.return_value = {"id": "entity-1"}
        result = _dispatch(
            "loom_graph_add_entity",
            {
                "label": "test",
                "entity_type": "TestEntity",
            },
        )
        assert result["id"] == "entity-1"

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


class TestAsyncResolve:
    def test_async_dispatch_returns_task_id(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _dispatch_resolve_issue_async,
            _dispatch_resolve_issue_status,
        )

        with (
            patch(
                "loom_ai.mcp_server._dispatch_resolve_issue",
                return_value={"success": True, "error": "", "plan": "", "pr_url": ""},
            ),
            patch("loom_ai.mcp_server._persist_task"),
        ):
            result = _dispatch_resolve_issue_async({"issue_number": 1})
        assert "task_id" in result
        assert result["status"] == "queued"

        status = _dispatch_resolve_issue_status({"task_id": result["task_id"]})
        assert status["task_id"] == result["task_id"]
        assert status["status"] in ("queued", "running", "complete")

        import time

        time.sleep(0.5)
        with _ASYNC_LOCK:
            _ASYNC_TASKS.pop(result["task_id"], None)

    def test_status_unknown_task(self):
        from loom_ai.mcp_server import _dispatch_resolve_issue_status

        result = _dispatch_resolve_issue_status({"task_id": "nonexistent"})
        assert "error" in result

    def test_cancel_running_task(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _AsyncTask,
            _dispatch_resolve_issue_cancel,
        )

        task = _AsyncTask(
            task_id="test-cancel",
            status="running",
            progress="Working...",
            created_at=1000.0,
        )
        with _ASYNC_LOCK:
            _ASYNC_TASKS["test-cancel"] = task
        with patch("loom_ai.mcp_server._persist_task"):
            result = _dispatch_resolve_issue_cancel({"task_id": "test-cancel"})
        assert result["status"] == "cancelled"
        with _ASYNC_LOCK:
            _ASYNC_TASKS.pop("test-cancel", None)

    def test_cancel_unknown_task(self):
        from loom_ai.mcp_server import _dispatch_resolve_issue_cancel

        result = _dispatch_resolve_issue_cancel({"task_id": "no-such-task"})
        assert "error" in result

    def test_cancel_already_complete(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _AsyncTask,
            _dispatch_resolve_issue_cancel,
        )

        task = _AsyncTask(
            task_id="test-done",
            status="complete",
            progress="Done.",
            created_at=1000.0,
        )
        with _ASYNC_LOCK:
            _ASYNC_TASKS["test-done"] = task
        result = _dispatch_resolve_issue_cancel({"task_id": "test-done"})
        assert result["message"] == "Task already finished"
        with _ASYNC_LOCK:
            _ASYNC_TASKS.pop("test-done", None)

    def test_cleanup_removes_expired(self):
        import time

        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _TASK_TTL_SECONDS,
            _AsyncTask,
            _cleanup_tasks,
        )

        task = _AsyncTask(
            task_id="old-task",
            status="complete",
            progress="Done.",
            created_at=time.time() - _TASK_TTL_SECONDS - 10,
        )
        with _ASYNC_LOCK:
            _ASYNC_TASKS["old-task"] = task
        _cleanup_tasks()
        with _ASYNC_LOCK:
            assert "old-task" not in _ASYNC_TASKS

    def test_async_stores_timeout_and_token(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _dispatch_resolve_issue_async,
        )

        with (
            patch(
                "loom_ai.mcp_server._dispatch_resolve_issue",
                return_value={"success": True, "error": "", "plan": "", "pr_url": ""},
            ),
            patch("loom_ai.mcp_server._persist_task"),
        ):
            result = _dispatch_resolve_issue_async(
                {
                    "issue_number": 99,
                    "timeout": 60,
                    "progress_token": "tok-123",
                }
            )
        tid = result["task_id"]
        import time

        time.sleep(0.1)
        with _ASYNC_LOCK:
            task = _ASYNC_TASKS.get(tid)
            assert task is not None
            assert task.timeout == 60.0
            assert task.progress_token == "tok-123"
            assert task.created_at > 0
            _ASYNC_TASKS.pop(tid, None)

    def test_cancel_tool_definition_exists(self):
        names = [t["name"] for t in _TOOLS]
        assert "loom_resolve_issue_cancel" in names

    def test_cancel_dispatch_table_entry(self):
        assert "loom_resolve_issue_cancel" in _DISPATCH_TABLE


class TestTaskPersistence:
    def test_task_to_dict_roundtrip(self):
        from loom_ai.mcp_server import (
            _AsyncTask,
            _dict_to_task,
            _task_to_dict,
        )

        original = _AsyncTask(
            task_id="abc123",
            status="running",
            progress="Working...",
            result={"key": "val"},
            error="",
            created_at=1000.0,
            cancelled=False,
            timeout=300.0,
            progress_token="tok-1",
        )
        d = _task_to_dict(original)
        restored = _dict_to_task(d)
        assert restored.task_id == original.task_id
        assert restored.status == original.status
        assert restored.result == original.result
        assert restored.timeout == original.timeout
        assert restored.progress_token == "tok-1"

    def test_persist_task_calls_api(self):
        from loom_ai.mcp_server import (
            _AsyncTask,
            _persist_task,
        )

        task = _AsyncTask(
            task_id="persist-test",
            status="queued",
            progress="Queued.",
            created_at=1000.0,
        )
        with patch("loom_ai.mcp_server._api") as mock_api:
            _persist_task(task)
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        assert call_args[0][0] == "POST"
        assert "/knowledge/documents" in call_args[0][1]
        body = call_args[0][2]
        assert body["id"] == "mcp-task-persist-test"
        assert body["category"] == "mcp_task"

    def test_persist_task_best_effort(self):
        from loom_ai.mcp_server import (
            _AsyncTask,
            _persist_task,
        )

        task = _AsyncTask(
            task_id="fail-test",
            status="running",
            progress="x",
            created_at=1000.0,
        )
        with patch(
            "loom_ai.mcp_server._api",
            side_effect=Exception("down"),
        ):
            _persist_task(task)

    def test_load_task_returns_task(self):
        from loom_ai.mcp_server import _load_task

        stored = json.dumps(
            {
                "task_id": "load-test",
                "status": "complete",
                "progress": "Done.",
                "result": {"ok": True},
                "error": "",
                "created_at": 1000.0,
                "cancelled": False,
                "timeout": 300.0,
                "progress_token": "",
            }
        )
        with patch(
            "loom_ai.mcp_server._api",
            return_value={
                "id": "mcp-task-load-test",
                "content": stored,
            },
        ):
            task = _load_task("load-test")
        assert task is not None
        assert task.task_id == "load-test"
        assert task.status == "complete"

    def test_load_task_returns_none_on_404(self):
        from loom_ai.mcp_server import _load_task

        with patch(
            "loom_ai.mcp_server._api",
            side_effect=Exception("404"),
        ):
            assert _load_task("missing") is None

    def test_load_task_handles_corrupt_json(self):
        from loom_ai.mcp_server import _load_task

        with patch(
            "loom_ai.mcp_server._api",
            return_value={"content": "not-json!!!"},
        ):
            assert _load_task("corrupt") is None

    def test_status_falls_back_to_storage(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _dispatch_resolve_issue_status,
        )

        with _ASYNC_LOCK:
            _ASYNC_TASKS.pop("fb-test", None)
        stored = json.dumps(
            {
                "task_id": "fb-test",
                "status": "complete",
                "progress": "Done.",
                "result": None,
                "error": "",
                "created_at": 1000.0,
                "cancelled": False,
                "timeout": 300.0,
                "progress_token": "",
            }
        )
        with patch(
            "loom_ai.mcp_server._api",
            return_value={
                "id": "mcp-task-fb-test",
                "content": stored,
            },
        ):
            result = _dispatch_resolve_issue_status({"task_id": "fb-test"})
        assert result["task_id"] == "fb-test"
        assert result["status"] == "complete"
        with _ASYNC_LOCK:
            _ASYNC_TASKS.pop("fb-test", None)

    def test_recover_tasks_marks_running_as_failed(
        self,
    ):
        import time

        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _recover_tasks,
        )

        docs = [
            {
                "category": "mcp_task",
                "content": json.dumps(
                    {
                        "task_id": "recover-1",
                        "status": "running",
                        "progress": "x",
                        "created_at": time.time(),
                        "timeout": 300.0,
                    }
                ),
            },
            {
                "category": "mcp_task",
                "content": json.dumps(
                    {
                        "task_id": "recover-2",
                        "status": "complete",
                        "progress": "Done",
                        "created_at": time.time(),
                        "timeout": 300.0,
                    }
                ),
            },
        ]
        with patch(
            "loom_ai.mcp_server._api",
            return_value={"documents": docs},
        ):
            _recover_tasks()
        with _ASYNC_LOCK:
            t1 = _ASYNC_TASKS.get("recover-1")
            t2 = _ASYNC_TASKS.get("recover-2")
            assert t1 is not None
            assert t1.status == "failed"
            assert "restart" in t1.error
            assert t2 is not None
            assert t2.status == "complete"
            _ASYNC_TASKS.pop("recover-1", None)
            _ASYNC_TASKS.pop("recover-2", None)

    def test_recover_skips_expired(self):
        from loom_ai.mcp_server import (
            _ASYNC_LOCK,
            _ASYNC_TASKS,
            _TASK_TTL_SECONDS,
            _recover_tasks,
        )

        docs = [
            {
                "category": "mcp_task",
                "content": json.dumps(
                    {
                        "task_id": "old-1",
                        "status": "complete",
                        "progress": "Done",
                        "created_at": 1.0,
                        "timeout": 300.0,
                    }
                ),
            },
        ]
        with patch(
            "loom_ai.mcp_server._api",
            return_value={"documents": docs},
        ):
            _recover_tasks()
        with _ASYNC_LOCK:
            assert "old-1" not in _ASYNC_TASKS


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
