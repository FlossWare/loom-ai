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
from typing import Any, Protocol, runtime_checkable

from loom_ai.backends.code_actions import (
    apply_diff,
    run_linter,
    run_tests,
)
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.session_persistence import SessionManager

logger = logging.getLogger(__name__)


@runtime_checkable
class ProgressCallback(Protocol):
    """Callback for streaming progress updates from DemoAgent."""

    def report(self, stage: str, message: str, progress_pct: float) -> None: ...


class _NullProgress:
    """No-op progress callback (default)."""

    def report(self, stage: str, message: str, progress_pct: float) -> None:
        pass


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
    pr_url: str = ""


async def _git(
    *args: str,
    cwd: str,
) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
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
        git_name: str | None = None,
        git_email: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._llm = llm
        self._workspace = workspace
        self._session = session_manager or SessionManager()
        self._git_name = git_name or os.environ.get("LOOM_GIT_NAME", "loom-ai")
        self._git_email = git_email or os.environ.get(
            "LOOM_GIT_EMAIL", "loom-ai@users.noreply.github.com"
        )
        self._progress: ProgressCallback = on_progress or _NullProgress()

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
                    "LOOM_LLM_MODEL",
                    "gpt-4o-mini",
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

        session_mgr = cls._build_session_manager()
        return cls(llm=llm, workspace=ws, session_manager=session_mgr)

    @staticmethod
    def _build_session_manager() -> SessionManager:
        """Build a SessionManager with available backends."""
        try:
            from loom_ai.backends.knowledge import (
                InMemoryKnowledgePipeline,
                TokenChunker,
            )
            from loom_ai.backends.memory import InMemoryPersistentMemory

            memory = InMemoryPersistentMemory()
            knowledge = InMemoryKnowledgePipeline(TokenChunker())
            logger.info("SessionManager wired with in-memory backends")
            return SessionManager(memory=memory, knowledge=knowledge)
        except Exception as exc:
            logger.warning("Session backend init failed: %s", exc)
            return SessionManager()

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
            "log",
            "--oneline",
            "-20",
            cwd=ws,
        )
        tree = await _git(
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            cwd=ws,
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
            parsed = json.loads(raw[raw.find("[") : raw.rfind("]") + 1] or "[]")
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

    _MAX_REVIEW_ATTEMPTS = 3
    _REVIEW_VOTES_NEEDED = 2
    _REVIEW_ROUNDS = 3

    async def _commit_and_pr(
        self,
        issue_number: int,
        changed_files: list[str],
    ) -> dict:
        """Create a branch, commit changes, push, and open a PR."""
        branch = f"fix/issue-{issue_number}"
        existing = await _git("branch", "--list", branch, cwd=self._workspace)
        if existing.strip():
            for suffix in range(2, 11):
                candidate = f"{branch}-{suffix}"
                check = await _git("branch", "--list", candidate, cwd=self._workspace)
                if not check.strip():
                    branch = candidate
                    break
        await _git("checkout", "-b", branch, cwd=self._workspace)
        for f in changed_files:
            await _git("add", f, cwd=self._workspace)
        await _git(
            "-c",
            f"user.name={self._git_name}",
            "-c",
            f"user.email={self._git_email}",
            "commit",
            "-m",
            f"fix: resolve issue #{issue_number}",
            cwd=self._workspace,
        )
        await _git(
            "push",
            "--set-upstream",
            "origin",
            branch,
            cwd=self._workspace,
        )
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "create",
            "--head",
            branch,
            "--base",
            "main",
            "--title",
            f"fix: resolve issue #{issue_number}",
            "--body",
            f"Fixes #{issue_number}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._workspace,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"gh pr create failed: {stderr.decode(errors='replace')}"
            )
        pr_url = stdout.decode(errors="replace").strip()
        return {"branch": branch, "pr_url": pr_url}

    async def _get_diff(self) -> str:
        """Return git diff of uncommitted changes in the workspace."""
        return await _git("diff", cwd=self._workspace)

    @staticmethod
    def _parse_review_response(
        response: str,
    ) -> tuple[bool, list[str]]:
        """Parse a single review response into (approved, issues)."""
        if "APPROVE" in response.upper():
            return True, []
        issues: list[str] = []
        for line in response.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            if upper == "REJECT":
                continue
            if upper.startswith("REJECT"):
                stripped = stripped.split(":", 1)[-1].strip()
            if stripped:
                issues.append(stripped)
        return False, issues

    async def _review_changes(
        self,
        diff: str,
        context: str,
    ) -> dict:
        """Send diff to the LLM multiple times for diverse review.

        Returns ``{"approved": bool, "issues": list[str], "votes": int}``.
        Approval requires at least ``_REVIEW_VOTES_NEEDED`` of
        ``_REVIEW_ROUNDS`` votes.
        """
        system = (
            "You are a strict code reviewer for the loom-ai project. "
            "Review the git diff below against the issue context. "
            "Check for correctness, security, and style. "
            "Respond with APPROVE if the changes are correct, or "
            "REJECT followed by a numbered list of specific issues."
        )
        prompt = f"## Context\n{context[:2000]}\n\n## Diff\n{diff[:4000]}"

        votes = 0
        all_issues: list[str] = []

        for _ in range(self._REVIEW_ROUNDS):
            try:
                response = await self._chat(prompt, system=system)
                ok, issues = self._parse_review_response(response)
                if ok:
                    votes += 1
                else:
                    all_issues.extend(issues)
            except Exception as exc:
                logger.warning("Review call failed: %s", exc)

        return {
            "approved": votes >= self._REVIEW_VOTES_NEEDED,
            "issues": all_issues,
            "votes": votes,
        }

    async def _fetch_issue(
        self,
        issue_number: int,
    ) -> str:
        """Fetch issue text from GitHub CLI."""
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            "FlossWare/loom-ai",
            cwd=self._workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def _build_context(
        self,
        issue_text: str,
        sid: str,
    ) -> str:
        """Gather repo context and append prior knowledge."""
        context = await self._gather_context(issue_text)
        logger.info("Gathered repo context (%d chars)", len(context))

        prior = await self._session.recover_context(
            project="loom-ai",
            query=issue_text[:200],
        )
        if prior.knowledge:
            context += "\n\n## Prior knowledge\n" + "\n".join(
                k["content"][:500] for k in prior.knowledge[:3]
            )
            await self._session.record_event(
                sid,
                f"recovered {len(prior.knowledge)} prior findings",
                kind="observation",
            )
        return context

    async def _try_attempt(
        self,
        plan: str,
        context: str,
        attempt: int,
        result: AgentResult,
        sid: str,
    ) -> tuple[bool | None, str]:
        """Run one implement-review attempt.

        Returns ``(approved_or_none, updated_context)``.
        ``None`` means no changes were applied (caller should stop).
        """
        changes = await self._implement(plan, context)
        result.changes = changes
        applied = [c for c in changes if c.get("result", {}).get("applied")]
        logger.info(
            "Applied %d/%d changes (attempt %d)",
            len(applied),
            len(changes),
            attempt + 1,
        )

        for c in applied:
            await self._session.record_event(
                sid,
                f"applied diff to {c.get('file', '?')}",
                kind="fix",
            )

        if not applied:
            result.error = "No changes applied"
            return None, context

        diff = await self._get_diff()
        if not diff:
            logger.info("No diff detected, skipping review")
            return True, context

        review = await self._review_changes(diff, context)
        logger.info(
            "Review attempt %d: %d/%d votes, approved=%s",
            attempt + 1,
            review["votes"],
            self._REVIEW_ROUNDS,
            review["approved"],
        )
        await self._session.record_event(
            sid,
            f"review attempt {attempt + 1}: "
            f"{review['votes']}/{self._REVIEW_ROUNDS} approved",
            kind="observation",
        )

        if review["approved"]:
            return True, context

        if review["issues"]:
            feedback = "\n".join(review["issues"][:5])
            context += f"\n\n## Review feedback (attempt {attempt + 1})\n{feedback}"
            logger.warning(
                "Review rejected (attempt %d), retrying: %s",
                attempt + 1,
                feedback[:200],
            )
        return False, context

    async def _resolve_issue_text(
        self,
        issue_number: int | None,
        issue_text: str,
    ) -> str:
        """Return issue text, fetching from GitHub if needed."""
        if not issue_text and issue_number:
            issue_text = await self._fetch_issue(issue_number)
        return issue_text

    async def _finalize(
        self,
        result: AgentResult,
        auto_pr: bool,
        issue_number: int | None,
    ) -> None:
        """Run lint, tests, and optionally create a PR."""
        result.lint_result = await run_linter(workspace=self._workspace)
        result.test_result = await run_tests(workspace=self._workspace)
        result.success = result.test_result.get("exit_code") == 0
        if not (auto_pr and result.success):
            return
        changed = [
            c["file"] for c in result.changes if c.get("result", {}).get("applied")
        ]
        if changed:
            pr_info = await self._commit_and_pr(issue_number or 0, changed)
            result.pr_url = pr_info["pr_url"]

    async def _run_review_loop(
        self,
        plan: str,
        context: str,
        result: AgentResult,
        sid: str,
    ) -> bool:
        """Run implement-review attempts, returning whether approved."""
        for attempt in range(self._MAX_REVIEW_ATTEMPTS):
            self._progress.report(
                "review",
                f"Review round {attempt + 1}/{self._MAX_REVIEW_ATTEMPTS}",
                55 + (attempt + 1) * 5,
            )
            status, context = await self._try_attempt(
                plan,
                context,
                attempt,
                result,
                sid,
            )
            if status is None:
                return False
            if status:
                return True
        return False

    async def run(
        self,
        issue_number: int | None = None,
        issue_text: str = "",
        *,
        auto_pr: bool = False,
    ) -> AgentResult:
        """Execute the full agent loop for an issue."""
        result = AgentResult(issue=issue_number or 0)

        sid = await self._session.create_session(
            project="loom-ai",
            metadata={"issue": issue_number or 0},
        )

        self._progress.report("fetch", "Fetching issue...", 10)
        if not issue_text and issue_number:
            try:
                issue_text = await self._fetch_issue(issue_number)
            except Exception as exc:
                result.error = f"Failed to fetch issue: {exc}"
                return result

        if not issue_text:
            result.error = "No issue text provided"
            return result

        try:
            self._progress.report("context", "Gathering repo context...", 20)
            context = await self._build_context(issue_text, sid)
            self._progress.report("plan", "Planning implementation...", 35)
            plan = await self._plan(context)
            result.plan = plan
            logger.info("Generated plan (%d chars)", len(plan))
            await self._session.record_event(
                sid,
                f"planned {len(plan)} chars",
                kind="decision",
            )

            self._progress.report("implement", "Implementing changes...", 55)
            approved = await self._run_review_loop(
                plan,
                context,
                result,
                sid,
            )

            if approved:
                self._progress.report("finalize", "Running lint and tests...", 80)
                await self._finalize(result, auto_pr, issue_number)
                self._progress.report("done", "Complete.", 100)
            elif not result.error:
                result.error = (
                    f"Review not approved after {self._MAX_REVIEW_ATTEMPTS} attempts"
                )

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
        "--issue",
        type=int,
        help="GitHub issue number",
    )
    parser.add_argument(
        "--workspace",
        default=os.getcwd(),
        help="Repo path",
    )
    parser.add_argument(
        "--issue-text",
        default="",
        help="Issue text (instead of fetching)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    agent = await DemoAgent.create(workspace=args.workspace)
    result = await agent.run(
        issue_number=args.issue,
        issue_text=args.issue_text,
    )

    print(
        json.dumps(
            {
                "issue": result.issue,
                "success": result.success,
                "changes_applied": len(
                    [c for c in result.changes if c.get("result", {}).get("applied")]
                ),
                "test_passed": result.test_result.get("passed", 0),
                "test_failed": result.test_result.get("failed", 0),
                "error": result.error,
            },
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
