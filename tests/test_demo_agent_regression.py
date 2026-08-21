"""Regression coverage retained while the dogfood tests are focused."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from loom_ai.demo_agent import DemoAgent
from loom_ai.models import ChatResponse


def _make_llm(responses: list[str]) -> MagicMock:
    llm = MagicMock()
    values = iter(responses)

    async def chat(messages, **kwargs):
        return ChatResponse(content=next(values))

    llm.chat = chat
    return llm


def test_mcp_resolve_issue_tool_contract_is_preserved():
    from loom_ai.mcp_server import _DISPATCH_TABLE, _TOOLS

    names = {tool["name"] for tool in _TOOLS}
    assert "loom_resolve_issue" in names
    assert "loom_resolve_issue_async" in names
    assert "loom_resolve_issue_status" in names
    assert "loom_resolve_issue" in _DISPATCH_TABLE
    assert "loom_resolve_issue_async" in _DISPATCH_TABLE
    assert "loom_resolve_issue_status" in _DISPATCH_TABLE

    tool = next(tool for tool in _TOOLS if tool["name"] == "loom_resolve_issue")
    assert "issue_number" in tool["inputSchema"]["required"]


def test_mcp_progress_reporter_contract_is_preserved():
    from loom_ai.mcp_progress import MCPProgressReporter

    output = StringIO()
    reporter = MCPProgressReporter(token="regression-token")
    with patch("sys.stdout", output):
        reporter.report("plan", "Planning...", 35.0)

    text = output.getvalue()
    assert "Content-Length:" in text
    assert "notifications/progress" in text
    assert "regression-token" in text


async def test_demo_agent_emits_progress_stages(tmp_path):
    stages: list[str] = []

    class Recorder:
        def report(self, stage, message, progress_pct):
            stages.append(stage)

    (tmp_path / "dummy.py").write_text("x = 1\n")
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", ".", "-A"], cwd=tmp_path, check=True)
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
        cwd=tmp_path,
        check=True,
    )

    agent = DemoAgent(
        llm=_make_llm(["plan", "[]"]),
        workspace=str(tmp_path),
        on_progress=Recorder(),
    )
    await agent.run(issue_text="Fix the thing")

    assert "fetch" in stages
    assert "context" in stages
    assert "plan" in stages
