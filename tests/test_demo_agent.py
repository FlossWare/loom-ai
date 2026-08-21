"""Tests for DemoAgent (#682)."""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

from loom_ai.demo_agent import AgentResult, DemoAgent
from loom_ai.mcp_server import _DISPATCH_TABLE, _TOOLS
from loom_ai.models import ChatResponse


def _make_llm(responses: list[str] | None = None) -> MagicMock:
    """Create a mock LLM backend that returns canned responses."""
    llm = MagicMock()
    resps = list(responses or ["plan", "[]"])
    call_count = 0

    async def _chat(messages, **kwargs):
        nonlocal call_count
        content = resps[min(call_count, len(resps) - 1)]
        call_count += 1
        return ChatResponse(content=content)

    llm.chat = _chat
    return llm


def _git_init(path, *, add_all: bool = False):
    """Initialise a git repo, optionally staging and committing all files."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        check=True,
    )
    if add_all:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", ".", "-A"],
            cwd=path,
            check=True,
        )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
            "-q",
        ],
        cwd=path,
        check=True,
    )


class TestDemoAgentInit:
    def test_constructs_with_llm_and_workspace(self, tmp_path):
        llm = _make_llm()
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        assert agent._workspace == str(tmp_path)

    async def test_create_with_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOOM_LLM_BASE_URL", "http://test:8080/v1")
        monkeypatch.setenv("LOOM_LLM_API_KEY", "test-key")
        agent = await DemoAgent.create(workspace=str(tmp_path))
        assert agent._workspace == str(tmp_path)


class TestAgentRun:
    async def test_returns_error_without_issue(self, tmp_path):
        llm = _make_llm()
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run()
        assert result.error == "No issue text provided"

    async def test_plans_and_reports(self, tmp_path):
        (tmp_path / "sample.py").write_text('x = "old"\n')
        _git_init(tmp_path, add_all=True)

        plan_json = '{"files": [{"path": "sample.py"}]}'
        changes_json = (
            '[{"file": "sample.py", "search": "\\"old\\"", "replace": "\\"new\\""}]'
        )
        llm = _make_llm(
            [
                plan_json,
                changes_json,
                "APPROVE",
                "APPROVE",
                "APPROVE",
            ]
        )
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))

        result = await agent.run(
            issue_text="Change old to new in sample.py",
        )
        assert result.plan == plan_json
        assert len(result.changes) == 1
        assert result.changes[0]["result"]["applied"] is True

        content = (tmp_path / "sample.py").read_text()
        assert '"new"' in content

    async def test_handles_no_changes(self, tmp_path):
        _git_init(tmp_path)

        llm = _make_llm(["plan", "[]"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(issue_text="Do nothing")
        assert result.error == "No changes applied"

    async def test_handles_bad_json(self, tmp_path):
        _git_init(tmp_path)

        llm = _make_llm(["plan", "not valid json"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(issue_text="Bad JSON test")
        assert result.error == "No changes applied"


class TestReviewLoop:
    async def test_review_approves_with_majority(self, tmp_path):
        llm = _make_llm(["APPROVE", "REJECT: bad style", "APPROVE"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        review = await agent._review_changes("diff content", "context")
        assert review["approved"] is True
        assert review["votes"] == 2

    async def test_review_rejects_without_majority(self, tmp_path):
        llm = _make_llm(
            [
                "REJECT: bug on line 5",
                "APPROVE",
                "REJECT: missing test",
            ]
        )
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        review = await agent._review_changes("diff content", "context")
        assert review["approved"] is False
        assert review["votes"] == 1
        assert len(review["issues"]) > 0

    async def test_review_handles_llm_errors(self, tmp_path):
        llm = _make_llm(["APPROVE"])

        async def _failing_chat(messages, **kwargs):
            raise RuntimeError("LLM down")

        llm.chat = _failing_chat
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        review = await agent._review_changes("diff", "ctx")
        assert review["approved"] is False
        assert review["votes"] == 0

    async def test_get_diff(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello\n")
        _git_init(tmp_path, add_all=True)
        (tmp_path / "f.txt").write_text("world\n")

        agent = DemoAgent(
            llm=_make_llm(),
            workspace=str(tmp_path),
        )
        diff = await agent._get_diff()
        assert "hello" in diff
        assert "world" in diff

    async def test_retry_on_rejection(self, tmp_path):
        (tmp_path / "sample.py").write_text('x = "old"\n')
        _git_init(tmp_path, add_all=True)

        plan_json = '{"files": [{"path": "sample.py"}]}'
        changes_json = (
            '[{"file": "sample.py", "search": "\\"old\\"", "replace": "\\"new\\""}]'
        )
        llm = _make_llm(
            [
                plan_json,
                changes_json,
                "REJECT: needs test",
                "REJECT",
                "REJECT",
                changes_json,
                "APPROVE",
                "APPROVE",
                "APPROVE",
            ]
        )
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(
            issue_text="Change old to new",
        )
        assert result.plan == plan_json


class TestParseReviewResponse:
    def test_approve(self):
        ok, issues = DemoAgent._parse_review_response("APPROVE")
        assert ok is True
        assert issues == []

    def test_reject_with_issues(self):
        ok, issues = DemoAgent._parse_review_response(
            "REJECT: bug on line 5\nmissing test",
        )
        assert ok is False
        assert "bug on line 5" in issues
        assert "missing test" in issues

    def test_bare_reject(self):
        ok, issues = DemoAgent._parse_review_response("REJECT")
        assert ok is False
        assert issues == []


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(issue=42)
        assert r.issue == 42
        assert r.success is False
        assert r.changes == []

    def test_pr_url_default_empty(self):
        assert AgentResult(issue=1).pr_url == ""

    def test_pr_url_can_be_set(self):
        r = AgentResult(issue=1, pr_url="https://github.com/pr/1")
        assert r.pr_url == "https://github.com/pr/1"


class TestCommitAndPr:
    async def test_creates_branch_and_returns_pr_url(self, tmp_path):
        agent = DemoAgent(llm=_make_llm(), workspace=str(tmp_path))

        with patch("loom_ai.demo_agent._git", new_callable=AsyncMock) as mock_git:
            mock_git.return_value = ""

            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"https://github.com/FlossWare/loom-ai/pull/99\n",
                b"",
            )
            mock_proc.returncode = 0

            with patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                result = await agent._commit_and_pr(42, ["test.py"])

        assert result["branch"] == "fix/issue-42"
        assert result["pr_url"] == ("https://github.com/FlossWare/loom-ai/pull/99")
        assert mock_git.call_count >= 4


class TestRunAutoPr:
    async def test_accepts_auto_pr_kwarg(self, tmp_path):
        _git_init(tmp_path)
        llm = _make_llm(["plan", "[]"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(issue_text="test", auto_pr=True)
        assert isinstance(result, AgentResult)


class TestMcpResolveIssue:
    def test_tool_definition_exists(self):
        names = [t["name"] for t in _TOOLS]
        assert "loom_resolve_issue" in names

    def test_tool_requires_issue_number(self):
        tool = next(t for t in _TOOLS if t["name"] == "loom_resolve_issue")
        assert "issue_number" in tool["inputSchema"]["required"]

    def test_dispatch_table_has_entry(self):
        assert "loom_resolve_issue" in _DISPATCH_TABLE

    def test_async_tool_definitions_exist(self):
        names = [t["name"] for t in _TOOLS]
        assert "loom_resolve_issue_async" in names
        assert "loom_resolve_issue_status" in names

    def test_async_dispatch_table_entries(self):
        assert "loom_resolve_issue_async" in _DISPATCH_TABLE
        assert "loom_resolve_issue_status" in _DISPATCH_TABLE


class TestProgressCallback:
    def test_null_progress_is_noop(self):
        from loom_ai.demo_agent import _NullProgress

        progress = _NullProgress()
        progress.report("test", "message", 50.0)

    def test_progress_protocol_check(self):
        from loom_ai.demo_agent import ProgressCallback, _NullProgress

        assert isinstance(_NullProgress(), ProgressCallback)

    def test_mcp_reporter_writes_jsonrpc(self):
        from io import StringIO

        from loom_ai.mcp_progress import MCPProgressReporter

        buf = StringIO()
        reporter = MCPProgressReporter(token="test-token")
        with patch("sys.stdout", buf):
            reporter.report("plan", "Planning...", 35.0)
        output = buf.getvalue()
        assert "Content-Length:" in output
        assert "notifications/progress" in output
        assert "test-token" in output

    async def test_agent_calls_progress(self, tmp_path):
        stages = []

        class Recorder:
            def report(self, stage, message, progress_pct):
                stages.append(stage)

        (tmp_path / "dummy.py").write_text("x = 1\n")
        _git_init(tmp_path, add_all=True)
        llm = _make_llm(["plan", "[]"])
        agent = DemoAgent(
            llm=llm,
            workspace=str(tmp_path),
            on_progress=Recorder(),
        )
        await agent.run(issue_text="Fix the thing")
        assert "fetch" in stages
        assert "context" in stages
        assert "plan" in stages
