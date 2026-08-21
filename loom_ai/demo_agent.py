"""End-to-end Loom dogfood agent (orchestration layer).

Composes existing Loom contracts: LLM chat, code actions, session
persistence, run-state machine, and GitTransaction. Publication is
fail-closed: lint+tests must pass and GitTransaction.mark_verified()
must run before push/PR.

Reusable capabilities (model routing, resilience policies, etc.) belong
in standalone FlossWare repositories — this module only orchestrates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from loom_ai.backends.code_actions import apply_diff, run_linter, run_tests
from loom_ai.git_transaction import GitTransaction, TransactionPolicy
from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.session_persistence import SessionManager

logger = logging.getLogger(__name__)


@runtime_checkable
class ProgressCallback(Protocol):
    def report(self, stage: str, message: str, progress_pct: float) -> None: ...


class _NullProgress:
    def report(self, stage: str, message: str, progress_pct: float) -> None:
        pass


@dataclass
class AgentResult:
    """Outcome of a single dogfood agent run."""

    issue: int = 0
    plan: str = ""
    changes: list[dict] = field(default_factory=list)
    test_result: dict = field(default_factory=dict)
    lint_result: dict = field(default_factory=dict)
    success: bool = False
    error: str = ""
    pr_url: str = ""
    run_state: dict = field(default_factory=dict)
    lint_ok: bool | None = None
    test_ok: bool | None = None


async def _git(*args: str, cwd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {stderr.decode(errors='replace').strip()}"
        )
    return stdout.decode(errors="replace").strip()


class DemoAgent:
    """Orchestrate investigate → plan → implement → review → verify → publish."""

    _MAX_REVIEW_ATTEMPTS = 3
    _REVIEW_VOTES_NEEDED = 2
    _REVIEW_ROUNDS = 3

    def __init__(
        self,
        llm: Any,
        workspace: str,
        *,
        session_manager: SessionManager | None = None,
        git_name: str | None = None,
        git_email: str | None = None,
        on_progress: ProgressCallback | None = None,
        allow_push: bool = False,
    ) -> None:
        self._llm = llm
        self._workspace = workspace
        self._session = session_manager or SessionManager()
        self._allow_push = allow_push
        self._git_name = git_name or os.environ.get("LOOM_GIT_NAME", "loom-ai")
        self._git_email = git_email or os.environ.get(
            "LOOM_GIT_EMAIL", "loom-ai@users.noreply.github.com"
        )
        self._progress: ProgressCallback = on_progress or _NullProgress()
        self._transaction: GitTransaction | None = None

    @classmethod
    async def create(cls, workspace: str | None = None) -> DemoAgent:
        """Build agent from environment (LLM + session backends)."""
        ws = workspace or os.getcwd()
        llm = None
        base_url = os.environ.get("LOOM_LLM_BASE_URL")
        if base_url:
            from loom_ai.backends.http_llm import HttpLLMBackend

            llm = HttpLLMBackend(
                base_url=base_url,
                api_key=os.environ.get("LOOM_LLM_API_KEY", ""),
                default_model=os.environ.get("LOOM_LLM_MODEL", "gpt-4o-mini"),
            )
        if llm is None:
            try:
                from loom_ai.backends.free_model_router import FreeModelRouter

                llm = FreeModelRouter()
                await llm.initialize()
            except Exception as exc:
                logger.warning("FreeModelRouter unavailable: %s", exc)
        if llm is None:
            raise RuntimeError(
                "No LLM backend available. Set LOOM_LLM_BASE_URL or configure FreeModelRouter."
            )
        return cls(
            llm=llm,
            workspace=ws,
            session_manager=await cls._build_session_manager(),
        )

    @classmethod
    async def _build_session_manager(cls) -> SessionManager:
        """Wire session storage. PostgreSQL is fail-closed (no silent memory)."""
        storage = os.environ.get("LOOM_STORAGE", "memory")
        if storage == "postgresql":
            from loom_ai.backends.postgresql import (
                PostgresqlKnowledgeStore,
                PostgresqlPersistentMemory,
                get_shared_pool,
            )

            pool = await get_shared_pool()
            memory = await PostgresqlPersistentMemory.from_env(pool=pool)
            knowledge = await PostgresqlKnowledgeStore.from_env(pool=pool)
            logger.info("SessionManager wired with PostgreSQL")
            return SessionManager(memory=memory, knowledge=knowledge)
        if storage not in {"", "memory"}:
            raise RuntimeError(f"Unsupported LOOM_STORAGE backend: {storage}")
        from loom_ai.backends.knowledge import InMemoryKnowledgePipeline, TokenChunker
        from loom_ai.backends.memory import InMemoryPersistentMemory

        return SessionManager(
            memory=InMemoryPersistentMemory(),
            knowledge=InMemoryKnowledgePipeline(TokenChunker()),
        )

    async def _chat(self, prompt: str, *, system: str = "") -> str:
        msgs: list[ChatMessage] = []
        if system:
            msgs.append(ChatMessage(role="system", content=system))
        msgs.append(ChatMessage(role="user", content=prompt))
        resp: ChatResponse = await self._llm.chat(msgs)
        return resp.content

    async def _gather_context(self, issue_text: str) -> str:
        recent_log = await _git("log", "--oneline", "-20", cwd=self._workspace)
        tree = await _git("ls-tree", "-r", "--name-only", "HEAD", cwd=self._workspace)
        return (
            f"## Issue\n{issue_text}\n\n"
            f"## Recent commits\n{recent_log}\n\n"
            f"## File tree (truncated)\n{tree[:3000]}"
        )

    async def _plan(self, context: str) -> str:
        system = (
            "You are a senior software engineer working on loom-ai. "
            "Produce a concise implementation plan. List specific files, changes, "
            "and a test strategy. Output JSON with keys files and test_strategy."
        )
        return await self._chat(context, system=system)

    async def _implement(self, plan: str, context: str) -> list[dict]:
        system = (
            "You are implementing a plan. For each change output JSON with keys "
            "file, search, replace. Search must be an exact unique substring of "
            "the current file. Output a JSON array."
        )
        raw = await self._chat(
            f"## Plan\n{plan}\n\n## Context\n{context}", system=system
        )
        try:
            start, end = raw.find("["), raw.rfind("]")
            parsed = json.loads(
                raw[start : end + 1] if start >= 0 and end >= start else "[]"
            )
        except (ValueError, TypeError):
            logger.warning("Failed to parse LLM diff output")
            return []
        changes: list[dict] = []
        for change in parsed:
            if not isinstance(change, dict) or not all(
                k in change for k in ("file", "search", "replace")
            ):
                continue
            result = await apply_diff(
                change["file"],
                change["search"],
                change["replace"],
                workspace=self._workspace,
            )
            changes.append({**change, "result": result})
        return changes

    @staticmethod
    def _parse_review_response(response: str) -> tuple[bool, list[str]]:
        """Only an exact line ``APPROVE`` counts; prose mentions do not."""
        if any(line.strip().upper() == "APPROVE" for line in response.splitlines()):
            return True, []
        issues: list[str] = []
        for line in response.splitlines():
            stripped = line.strip()
            if not stripped or stripped.upper() == "REJECT":
                continue
            if stripped.upper().startswith("REJECT"):
                stripped = stripped.split(":", 1)[-1].strip()
            if stripped:
                issues.append(stripped)
        return False, issues

    async def _review_changes(self, diff: str, context: str) -> dict:
        system = (
            "You are a strict code reviewer for loom-ai. Review the diff for correctness, "
            "security and style. Respond on its own line with exactly APPROVE when correct, "
            "otherwise REJECT followed by specific issues."
        )
        prompt = f"## Context\n{context[:2000]}\n\n## Diff\n{diff[:4000]}"
        votes = 0
        all_issues: list[str] = []
        for _ in range(self._REVIEW_ROUNDS):
            try:
                ok, issues = self._parse_review_response(
                    await self._chat(prompt, system=system)
                )
                votes += int(ok)
                all_issues.extend(issues)
            except Exception as exc:
                logger.warning("Review call failed: %s", exc)
        return {
            "approved": votes >= self._REVIEW_VOTES_NEEDED,
            "issues": all_issues,
            "votes": votes,
        }

    async def _fetch_issue(self, issue_number: int) -> str:
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
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"gh issue view failed: {stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace")

    async def _build_context(self, issue_text: str, sid: str) -> str:
        self._progress.report("context", "Gathering repo context...", 20)
        context = await self._gather_context(issue_text)
        prior = await self._session.recover_context(
            project="loom-ai", query=issue_text[:200]
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
        self, plan: str, context: str, attempt: int, result: AgentResult, sid: str
    ) -> tuple[bool | None, str]:
        changes = await self._implement(plan, context)
        result.changes = changes
        applied = [c for c in changes if c.get("result", {}).get("applied")]
        for c in applied:
            await self._session.record_event(
                sid, f"applied diff to {c.get('file', '?')}", kind="fix"
            )
        if not applied:
            result.error = "No changes applied"
            return None, context
        diff = await _git("diff", cwd=self._workspace)
        if not diff:
            result.error = "No git diff detected after applying changes"
            return None, context
        review = await self._review_changes(diff, context)
        await self._session.record_event(
            sid,
            f"review attempt {attempt + 1}: {review['votes']}/{self._REVIEW_ROUNDS} approved",
            kind="observation",
        )
        if review["approved"]:
            return True, context
        # Rejected: restore workspace so the next attempt starts from a clean tree.
        # Without this, subsequent _implement calls fail because search text is gone.
        try:
            await _git("checkout", "--", ".", cwd=self._workspace)
            await _git("clean", "-fd", cwd=self._workspace)
        except Exception as reset_exc:
            logger.warning("Failed to reset workspace after reject: %s", reset_exc)
        if review["issues"]:
            context += "\n\n## Review feedback\n" + "\n".join(review["issues"][:5])
        return False, context

    async def _begin_publication(self, issue_number: int) -> None:
        if not self._allow_push:
            raise RuntimeError("Push/PR disabled; set allow_push=True to enable")
        tx = GitTransaction(
            self._workspace,
            TransactionPolicy(allow_dirty=False, require_verification=True),
        )
        await tx.begin()
        base = f"fix/issue-{issue_number}"
        branch = base
        for suffix in range(0, 10):
            candidate = base if suffix == 0 else f"{base}-{suffix + 1}"
            existing = await _git("branch", "--list", candidate, cwd=self._workspace)
            if not existing.strip():
                branch = candidate
                break
        await tx.create_branch(branch)
        self._transaction = tx

    async def _finalize(
        self, result: AgentResult, auto_pr: bool, issue_number: int | None
    ) -> None:
        result.lint_result = await run_linter(workspace=self._workspace)
        result.test_result = await run_tests(workspace=self._workspace)
        lint_ok = result.lint_result.get("exit_code", 1) == 0
        test_ok = result.test_result.get("exit_code", 1) == 0
        result.lint_ok = lint_ok
        result.test_ok = test_ok
        result.success = lint_ok and test_ok
        if not (auto_pr and result.success):
            return
        if self._transaction is None:
            raise RuntimeError("Publication transaction was not initialized")
        changed = list(
            dict.fromkeys(
                c["file"] for c in result.changes if c.get("result", {}).get("applied")
            )
        )
        if not changed:
            raise RuntimeError("No changed files available for publication")
        self._transaction.mark_verified()
        await self._transaction.stage_and_commit(
            changed,
            f"fix: resolve issue #{issue_number or 0}",
            author_name=self._git_name,
            author_email=self._git_email,
        )
        await self._transaction.push()
        result.pr_url = await self._transaction.create_pr(
            title=f"fix: resolve issue #{issue_number or 0}",
            body=f"Fixes #{issue_number or 0}\n\nVerification: lint and tests passed.",
        )

    async def _run_review_loop(
        self, plan: str, context: str, result: AgentResult, sid: str
    ) -> bool:
        for attempt in range(self._MAX_REVIEW_ATTEMPTS):
            self._progress.report(
                "review",
                f"Review round {attempt + 1}/{self._MAX_REVIEW_ATTEMPTS}",
                55 + (attempt + 1) * 5,
            )
            status, context = await self._try_attempt(
                plan, context, attempt, result, sid
            )
            if status is None:
                return False
            if status:
                return True
        return False

    async def _resolve_issue_text(
        self, issue_number: int | None, issue_text: str
    ) -> str:
        if not issue_text and issue_number:
            issue_text = await self._fetch_issue(issue_number)
        return issue_text

    async def run(
        self,
        issue_number: int | None = None,
        issue_text: str = "",
        *,
        auto_pr: bool = False,
    ) -> AgentResult:
        from loom_ai.run_state import RunPhase, RunStateMachine

        run_id = f"run-{issue_number or 0}"
        sm = RunStateMachine(run_id)
        result = AgentResult(issue=issue_number or 0)
        sid = await self._session.create_session(
            project="loom-ai", metadata={"issue": issue_number or 0}
        )
        try:
            sm.transition(RunPhase.FETCHING)
            self._progress.report("fetch", "Fetching issue...", 10)
            issue_text = await self._resolve_issue_text(issue_number, issue_text)
            if not issue_text:
                raise RuntimeError("No issue text provided")

            sm.transition(RunPhase.PLANNING)
            context = await self._build_context(issue_text, sid)
            self._progress.report("plan", "Planning implementation...", 35)
            plan = await self._plan(context)
            result.plan = plan
            await self._session.record_event(
                sid, f"planned {len(plan)} chars", kind="decision"
            )

            if auto_pr:
                await self._begin_publication(issue_number or 0)

            sm.transition(RunPhase.EXECUTING)
            self._progress.report("implement", "Implementing changes...", 55)
            approved = await self._run_review_loop(plan, context, result, sid)
            if not approved:
                result.error = result.error or (
                    f"Review not approved after {self._MAX_REVIEW_ATTEMPTS} attempts"
                )
                sm.fail()
                if self._transaction:
                    await self._transaction.rollback()
            else:
                sm.transition(RunPhase.VERIFYING)
                self._progress.report("finalize", "Running lint and tests...", 80)
                await self._finalize(result, auto_pr, issue_number)
                if not result.success:
                    result.error = result.error or "Verification failed"
                    sm.fail()
                    if self._transaction:
                        try:
                            await self._transaction.rollback()
                        except Exception as rollback_exc:
                            logger.error(
                                "Rollback after verification failure: %s", rollback_exc
                            )
                    await self._session.persist(sid)
                else:
                    sm.transition(RunPhase.PERSISTING)
                    await self._session.persist(sid)
                    sm.transition(RunPhase.COMPLETED)
                    if result.pr_url:
                        sm.transition(RunPhase.PUBLISHED)
                    self._progress.report("done", "Complete.", 100)
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


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Loom demo agent — resolve a GitHub issue"
    )
    parser.add_argument("--issue", type=int, help="GitHub issue number")
    parser.add_argument("--workspace", default=os.getcwd(), help="Repo path")
    parser.add_argument(
        "--auto-pr", action="store_true", help="Create and publish a PR"
    )
    args = parser.parse_args()
    agent = await DemoAgent.create(workspace=args.workspace)
    result = await agent.run(issue_number=args.issue, auto_pr=args.auto_pr)
    print(json.dumps(result.__dict__, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
