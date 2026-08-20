"""Tests for DemoAgent (#682)."""

from __future__ import annotations

from unittest.mock import MagicMock

from loom_ai.demo_agent import AgentResult, DemoAgent
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

        import subprocess
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_path, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", ".", "-A"],
            cwd=tmp_path, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-m", "init", "-q"],
            cwd=tmp_path, check=True,
        )

        plan_json = '{"files": [{"path": "sample.py"}]}'
        changes_json = (
            '[{"file": "sample.py", "search": '
            '"\\"old\\"", "replace": "\\"new\\""}]'
        )
        llm = _make_llm([plan_json, changes_json])
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
        import subprocess
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_path, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "init", "-q"],
            cwd=tmp_path, check=True,
        )

        llm = _make_llm(["plan", "[]"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(issue_text="Do nothing")
        assert result.error == "No changes applied"

    async def test_handles_bad_json(self, tmp_path):
        import subprocess
        subprocess.run(
            ["git", "init", "-q"], cwd=tmp_path, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "init", "-q"],
            cwd=tmp_path, check=True,
        )

        llm = _make_llm(["plan", "not valid json"])
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))
        result = await agent.run(issue_text="Bad JSON test")
        assert result.error == "No changes applied"


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(issue=42)
        assert r.issue == 42
        assert r.success is False
        assert r.changes == []
