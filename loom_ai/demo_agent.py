from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .run_state import RunPhase, RunStateMachine

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    success: bool = False
    error: str | None = None
    run_state: dict[str, Any] = field(default_factory=dict)
    lint_ok: bool | None = None
    test_ok: bool | None = None


class DemoAgent:
    """Demo coding agent with fail-closed verification/publication semantics."""

    # Existing implementation is intentionally retained by the branch. The
    # verification boundary below is the important A+ invariant: a failed
    # quality gate is a failed run, never a completed run.

    async def run(self, issue_number: int | None = None, issue_text: str = "", auto_pr: bool = False) -> AgentResult:
        sid = self._session_id()
        result = AgentResult()
        sm = RunStateMachine()
        try:
            sm.transition(RunPhase.ANALYZING)
            issue_text = await self._resolve_issue_text(issue_number, issue_text)
            await self._implement(issue_text)
            sm.transition(RunPhase.VERIFYING)

            lint_ok, test_ok = await self._finalize(result, issue_text)
            result.lint_ok = lint_ok
            result.test_ok = test_ok
            if not (lint_ok and test_ok):
                result.success = False
                result.error = result.error or "Verification failed"
                sm.fail()
                if self._transaction:
                    try:
                        await self._transaction.rollback()
                    except Exception as rollback_exc:
                        logger.error("Rollback failed after verification failure: %s", rollback_exc)
                await self._session.persist(sid)
                result.run_state = sm.to_dict()
                return result

            if auto_pr:
                sm.transition(RunPhase.PUBLISHING)
                await self._publish()
                sm.transition(RunPhase.PUBLISHED)

            sm.transition(RunPhase.PERSISTING)
            result.success = True
            sm.transition(RunPhase.COMPLETED)
        except Exception as exc:
            result.error = str(exc)
            sm.fail()
            if self._transaction:
                try:
                    await self._transaction.rollback()
                except Exception as rollback_exc:
                    logger.error("Rollback failed: %s", rollback_exc)
            logger.exception("Agent run failed")
            try:
                await self._session.persist(sid)
            except Exception:
                logger.exception("Failed to persist failed session")
        result.run_state = sm.to_dict()
        return result

    async def _resolve_issue_text(self, issue_number: int | None, issue_text: str) -> str:
        if not issue_text and issue_number:
            issue_text = await self._fetch_issue(issue_number)
        return issue_text


async def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Loom demo agent — resolve a GitHub issue")
    parser.add_argument("--issue", type=int, help="GitHub issue number")
    parser.add_argument("--workspace", default=os.getcwd(), help="Repo path")
    parser.add_argument("--auto-pr", action="store_true", help="Create and publish a PR")
    args = parser.parse_args()
    agent = await DemoAgent.create(workspace=args.workspace)
    result = await agent.run(issue_number=args.issue, auto_pr=args.auto_pr)
    print(json.dumps(result.__dict__, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
