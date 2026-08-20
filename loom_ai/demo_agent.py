"""End-to-end Loom agent that resolves a real issue.

Demonstrates the full Loom pipeline: read repo context, plan a fix via
LLM, apply changes via code actions, run tests, and report results.

Usage::

    python -m loom_ai.demo_agent --issue 123 --workspace /path/to/repo

    # Or programmatically:
    from loom_ai.demo_agent import DemoAgent
    agent = await DemoAgent.create(workspace="/path/to/repo")
    result = await agent.run(issue_number=123)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loom_ai.backends.code_actions import (
    apply_diff,
    run_linter,
    run_tests,
)
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.session_persistence import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Outcome of a single agent run."""

    issue: int
    plan: str = ""
    changes: list[dict] = field(default_factory=list)
    test_result: dict = field(default_factory=dict)
    lint_result: dict = field(default_factory=dict)
    success: bool = False
    error: str = ""


async def _git(
    *args: str, cwd: str,
) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace").strip()


async def _read_file(path: Path) -> str:
    """Read a file, returning empty string on error."""
    try:
        return path.read_text()
    except Exception:
        return ""


class DemoAgent:
    """Loom agent that resolves issues end-to-end.

    Uses any :class:`~loom_ai.protocols.LLMBackend` (including
    ``FreeModelRouter``) for planning and code generation.
    """

    def __init__(
        self,
        llm: Any,
        workspace: str,
        *,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._llm = llm
        self._workspace = workspace
        self._session = session_manager or SessionManager()

    @classmethod
    async def create(
        cls,
        workspace: str | None = None,
    ) -> DemoAgent:
        """Create agent from environment, auto-detecting LLM backend."""
        ws = workspace or os.getcwd()

        llm = None
        base_url = os.environ.get("LOOM_LLM_BASE_URL")
        if base_url:
            from loom_ai.backends.http_llm import HttpLLMBackend

            llm = HttpLLMBackend(
                base_url=base_url,
                api_key=os.environ.get("LOOM_LLM_API_KEY", ""),
                default_model=os.environ.get(
                    "LOOM_LLM_MODEL", "gpt-4o-mini",
                ),
            )

        if llm is None:
            try:
                from loom_ai.backends.free_model_router import (
                    FreeModelRouter,
                )

                llm = FreeModelRouter()
                await llm.initialize()
            except Exception as exc:
                logger.warning("FreeModelRouter unavailable: %s", exc)

        if llm is None:
            raise RuntimeError(
                "No LLM backend available. Set LOOM_LLM_BASE_URL or "
                "configure FreeModelRouter."
            )

        return cls(llm=llm, workspace=ws)

    async def _chat(
        self,
        prompt: str,
        *,
        system: str = "",
    ) -> str:
        msgs: list[ChatMessage] = []
        if system:
            msgs.append(ChatMessage(role="system", content=system))
        msgs.append(ChatMessage(role="user", content=prompt))
        resp: ChatResponse = await self._llm.chat(msgs)
        return resp.content

    async def _gather_context(
        self,
        issue_text: str,
    ) -> str:
        """Gather repo context relevant to the issue."""
        ws = self._workspace
        recent_log = await _git(
            "log", "--oneline", "-20", cwd=ws,
        )
        tree = await _git(
            "ls-tree", "-r", "--name-only", "HEAD", cwd=ws,
        )
        file_list = tree[:3000]

        return (
            f"## Issue\n{issue_text}\n\n"
            f"## Recent commits\n{recent_log}\n\n"
            f"## File tree (truncated)\n{file_list}"
        )

    async def _plan(
        self,
        context: str,
    ) -> str:
        """Ask the LLM to produce an implementation plan."""
        system = (
            "You are a senior software engineer working on the loom-ai "
            "project. Produce a concise implementation plan for the "
            "given issue. List specific files to modify, what to change "
            "in each, and a test strategy. Output JSON with keys: "
            '"files" (list of {path, changes}), "test_strategy".'
        )
        return await self._chat(context, system=system)

    async def _implement(
        self,
        plan: str,
        context: str,
    ) -> list[dict]:
        """Ask the LLM to generate diffs, then apply them."""
        system = (
            "You are implementing a plan. For each change, output JSON "
            "with keys: file, search, replace. The search text must be "
            "an exact unique substring of the current file content. "
            "Output a JSON array of changes."
        )
        prompt = f"## Plan\n{plan}\n\n## Context\n{context}"
        raw = await self._chat(prompt, system=system)

        changes: list[dict] = []
        try:
            parsed = json.loads(
                raw[raw.find("["):raw.rfind("]") + 1] or "[]"
            )
        except ValueError:
            logger.warning("Failed to parse LLM diff output")
            return changes

        for change in parsed:
            if not all(k in change for k in ("file", "search", "replace")):
                continue
            result = await apply_diff(
                change["file"],
                change["search"],
                change["replace"],
                workspace=self._workspace,
            )
            changes.append({**change, "result": result})
        return changes

    async def run(
        self,
        issue_number: int | None = None,
        issue_text: str = "",
    ) -> AgentResult:
        """Execute the full agent loop for an issue."""
        result = AgentResult(issue=issue_number or 0)

        sid = await self._session.create_session(
            project="loom-ai",
            metadata={"issue": issue_number or 0},
        )

        if not issue_text and issue_number:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "gh", "issue", "view", str(issue_number),
                    "--repo", "FlossWare/loom-ai",
                    cwd=self._workspace,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                issue_text = stdout.decode(errors="replace")
            except Exception as exc:
                result.error = f"Failed to fetch issue: {exc}"
                return result

        if not issue_text:
            result.error = "No issue text provided"
            return result

        try:
            context = await self._gather_context(issue_text)
            logger.info("Gathered repo context (%d chars)", len(context))

            prior = await self._session.recover_context(
                project="loom-ai",
                query=issue_text[:200],
            )
            if prior.knowledge:
                context += (
                    "\n\n## Prior knowledge\n"
                    + "\n".join(
                        k["content"][:500] for k in prior.knowledge[:3]
                    )
                )
                await self._session.record_event(
                    sid,
                    f"recovered {len(prior.knowledge)} prior findings",
                    kind="observation",
                )

            plan = await self._plan(context)
            result.plan = plan
            logger.info("Generated plan (%d chars)", len(plan))
            await self._session.record_event(
                sid, f"planned {len(plan)} chars", kind="decision",
            )

            changes = await self._implement(plan, context)
            result.changes = changes
            applied = [c for c in changes if c.get("result", {}).get("applied")]
            logger.info(
                "Applied %d/%d changes", len(applied), len(changes),
            )

            for c in applied:
                await self._session.record_event(
                    sid,
                    f"applied diff to {c.get('file', '?')}",
                    kind="fix",
                )

            if applied:
                lint = await run_linter(workspace=self._workspace)
                result.lint_result = lint

                tests = await run_tests(workspace=self._workspace)
                result.test_result = tests
                result.success = tests.get("exit_code") == 0
            else:
                result.error = "No changes applied"

        except Exception as exc:
            result.error = str(exc)
            logger.exception("Agent run failed")

        await self._session.persist(sid)
        return result


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Loom demo agent — resolve a GitHub issue",
    )
    parser.add_argument(
        "--issue", type=int, help="GitHub issue number",
    )
    parser.add_argument(
        "--workspace", default=os.getcwd(), help="Repo path",
    )
    parser.add_argument(
        "--issue-text", default="", help="Issue text (instead of fetching)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    agent = await DemoAgent.create(workspace=args.workspace)
    result = await agent.run(
        issue_number=args.issue,
        issue_text=args.issue_text,
    )

    print(json.dumps({
        "issue": result.issue,
        "success": result.success,
        "changes_applied": len([
            c for c in result.changes
            if c.get("result", {}).get("applied")
        ]),
        "test_passed": result.test_result.get("passed", 0),
        "test_failed": result.test_result.get("failed", 0),
        "error": result.error,
    }, indent=2))


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
