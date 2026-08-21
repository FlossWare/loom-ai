"""Run-level regression tests for failed verification and publication rollback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom_ai.demo_agent import DemoAgent
from loom_ai.models import ChatResponse


class _StubLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def chat(self, messages, **kwargs):
        return ChatResponse(content=next(self._responses))


def _approved_llm() -> _StubLLM:
    changes = '[{"file":"sample.py","search":"x = 1","replace":"x = 2"}]'
    return _StubLLM(
        [
            "plan",
            changes,
            "APPROVE",
            "APPROVE",
            "APPROVE",
        ]
    )


@pytest.mark.parametrize(
    ("lint_exit", "test_exit"),
    [
        (1, 0),
        (0, 1),
    ],
    ids=["lint-failure", "test-failure"],
)
async def test_verification_failure_fails_run_and_rolls_back(
    tmp_path, lint_exit: int, test_exit: int
) -> None:
    """Failed verification must fail the run and roll back publication."""
    (tmp_path / "sample.py").write_text("x = 1\n")

    agent = DemoAgent(_approved_llm(), str(tmp_path), allow_push=True)
    tx = MagicMock()
    tx.rollback = AsyncMock()
    agent._transaction = tx

    with (
        patch.object(agent, "_begin_publication", new=AsyncMock()),
        patch(
            "loom_ai.demo_agent.run_linter",
            new=AsyncMock(return_value={"exit_code": lint_exit}),
        ),
        patch(
            "loom_ai.demo_agent.run_tests",
            new=AsyncMock(return_value={"exit_code": test_exit}),
        ),
    ):
        result = await agent.run(issue_text="change x", auto_pr=True)

    assert not result.success
    assert result.lint_ok is (lint_exit == 0)
    assert result.test_ok is (test_exit == 0)
    assert result.run_state["phase"] == "failed"
    tx.mark_verified.assert_not_called()
    tx.stage_and_commit.assert_not_awaited()
    tx.push.assert_not_awaited()
    tx.create_pr.assert_not_awaited()
    tx.rollback.assert_awaited_once()
