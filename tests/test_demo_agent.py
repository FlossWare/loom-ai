"""Focused tests for the dogfood DemoAgent path."""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

from loom_ai.demo_agent import AgentResult, DemoAgent
from loom_ai.models import ChatResponse


def _make_llm(responses: list[str] | None = None) -> MagicMock:
    llm = MagicMock()
    values = list(responses or ["plan", "[]"])
    index = 0

    async def chat(messages, **kwargs):
        nonlocal index
        value = values[min(index, len(values) - 1)]
        index += 1
        return ChatResponse(content=value)

    llm.chat = chat
    return llm


def _git_init(path, *, add_all=False):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    if add_all:
        subprocess.run(["git", "add", ".", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=path,
        check=True,
    )


class TestReview:
    def test_explicit_approve(self):
        assert DemoAgent._parse_review_response("APPROVE") == (True, [])

    def test_prose_containing_approve_is_not_approval(self):
        ok, issues = DemoAgent._parse_review_response("I cannot APPROVE this change")
        assert not ok
        assert issues

    async def test_majority(self, tmp_path):
        agent = DemoAgent(_make_llm(["APPROVE", "REJECT: bug", "APPROVE"]), str(tmp_path))
        result = await agent._review_changes("diff", "context")
        assert result["approved"]
        assert result["votes"] == 2

    async def test_llm_failure_is_rejection(self, tmp_path):
        llm = _make_llm(["APPROVE"])

        async def fail(*args, **kwargs):
            raise RuntimeError("down")

        llm.chat = fail
        agent = DemoAgent(llm, str(tmp_path))
        result = await agent._review_changes("diff", "context")
        assert not result["approved"]
        assert result["votes"] == 0


class TestRun:
    async def test_no_issue_is_failure(self, tmp_path):
        result = await DemoAgent(_make_llm(), str(tmp_path)).run()
        assert not result.success
        assert result.error == "No issue text provided"

    async def test_changes_are_applied_and_reviewed(self, tmp_path):
        (tmp_path / "sample.py").write_text('x = "old"\n')
        _git_init(tmp_path, add_all=True)
        changes = '[{"file":"sample.py","search":"\\"old\\"","replace":"\\"new\\""}]'
        llm = _make_llm(["plan", changes, "APPROVE", "APPROVE", "APPROVE"])
        result = await DemoAgent(llm, str(tmp_path)).run(issue_text="change old to new")
        assert result.changes[0]["result"]["applied"]
        assert '"new"' in (tmp_path / "sample.py").read_text()
        assert result.run_state["phase"] == "completed"

    async def test_rejected_review_fails(self, tmp_path):
        (tmp_path / "sample.py").write_text("x = 1\n")
        _git_init(tmp_path, add_all=True)
        changes = '[{"file":"sample.py","search":"x = 1","replace":"x = 2"}]'
        llm = _make_llm(["plan", changes, "REJECT: bug", "REJECT", "REJECT"])
        result = await DemoAgent(llm, str(tmp_path)).run(issue_text="change x")
        assert not result.success
        assert "Review not approved" in result.error


class TestPublicationTransaction:
    async def test_auto_pr_requires_clean_workspace_and_uses_transaction(self, tmp_path):
        _git_init(tmp_path)
        agent = DemoAgent(_make_llm(), str(tmp_path), allow_push=True)
        tx = MagicMock()
        tx.begin = AsyncMock()
        tx.create_branch = AsyncMock(return_value="fix/issue-42")
        with patch("loom_ai.demo_agent.GitTransaction", return_value=tx):
            await agent._begin_publication(42)
        tx.begin.assert_awaited_once()
        tx.create_branch.assert_awaited_once_with("fix/issue-42")
        assert agent._transaction is tx

    async def test_finalize_requires_verification_before_publish(self, tmp_path):
        _git_init(tmp_path)
        agent = DemoAgent(_make_llm(), str(tmp_path), allow_push=True)
        tx = MagicMock()
        tx.stage_and_commit = AsyncMock()
        tx.push = AsyncMock()
        tx.create_pr = AsyncMock(return_value="https://github.com/FlossWare/loom-ai/pull/1")
        agent._transaction = tx
        result = AgentResult(issue=42, changes=[{"file": "x.py", "result": {"applied": True}}])
        with (
            patch("loom_ai.demo_agent.run_linter", return_value={"exit_code": 0}),
            patch("loom_ai.demo_agent.run_tests", return_value={"exit_code": 0}),
        ):
            await agent._finalize(result, True, 42)
        tx.mark_verified.assert_called_once()
        tx.stage_and_commit.assert_awaited_once()
        tx.push.assert_awaited_once()
        tx.create_pr.assert_awaited_once()
        assert result.pr_url.endswith("/1")

    async def test_lint_failure_cannot_publish(self, tmp_path):
        _git_init(tmp_path)
        agent = DemoAgent(_make_llm(), str(tmp_path), allow_push=True)
        tx = MagicMock()
        tx.stage_and_commit = AsyncMock()
        tx.push = AsyncMock()
        agent._transaction = tx
        result = AgentResult(issue=42, changes=[{"file": "x.py", "result": {"applied": True}}])
        with (
            patch("loom_ai.demo_agent.run_linter", return_value={"exit_code": 1}),
            patch("loom_ai.demo_agent.run_tests", return_value={"exit_code": 0}),
        ):
            await agent._finalize(result, True, 42)
        assert not result.success
        tx.mark_verified.assert_not_called()
        tx.push.assert_not_awaited()


class TestResult:
    def test_defaults(self):
        result = AgentResult(issue=42)
        assert not result.success
        assert result.pr_url == ""
