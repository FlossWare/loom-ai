"""Transactional, recoverable Git/PR operations."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self


@dataclass(frozen=True)
class GitSnapshot:
    """Captured state before any mutation."""

    branch: str
    head_sha: str
    is_dirty: bool
    tracked_files: frozenset[str]


@dataclass(frozen=True)
class TransactionPolicy:
    """Controls what the transaction allows."""

    allow_dirty: bool = False
    require_verification: bool = True
    max_push_retries: int = 2
    max_pr_retries: int = 1


class GitTransaction:
    """Wrap git mutations in a recoverable transaction."""

    def __init__(
        self,
        workspace: str | Path,
        policy: TransactionPolicy | None = None,
    ) -> None:
        self._ws = str(Path(workspace).resolve())
        self._policy = policy or TransactionPolicy()
        self._snapshot: GitSnapshot | None = None
        self._branch: str = ""
        self._committed = False
        self._pushed = False
        self._pr_url: str = ""
        self._verified = False

    async def begin(self) -> GitSnapshot:
        if self._snapshot is not None:
            raise RuntimeError("Transaction already started")
        branch = await self._git("rev-parse", "--abbrev-ref", "HEAD")
        head_sha = await self._git("rev-parse", "HEAD")
        status = await self._git("status", "--porcelain")
        is_dirty = bool(status.strip())
        tracked: set[str] = set()
        for line in status.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                tracked.add(parts[1])
        if is_dirty and not self._policy.allow_dirty:
            raise RuntimeError("Workspace is dirty and policy forbids it")
        self._snapshot = GitSnapshot(
            branch=branch,
            head_sha=head_sha,
            is_dirty=is_dirty,
            tracked_files=frozenset(tracked),
        )
        return self._snapshot

    async def create_branch(self, name: str) -> str:
        self._require_started()
        await self._git("checkout", "-b", name)
        self._branch = name
        return name

    def mark_verified(self) -> None:
        """Authorize publication after independent verification has passed."""
        self._require_started()
        self._verified = True

    async def stage_and_commit(
        self,
        files: list[str],
        message: str,
        *,
        author_name: str,
        author_email: str,
    ) -> str:
        self._require_started()
        for f in files:
            await self._git("add", str(f))
        diff = await self._git("diff", "--cached", "--name-only")
        if not diff.strip():
            return await self._git("rev-parse", "HEAD")
        await self._git(
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
        )
        self._committed = True
        return await self._git("rev-parse", "HEAD")

    async def push(self) -> None:
        if not self._committed:
            raise RuntimeError("Nothing to push")
        if self._policy.require_verification and not self._verified:
            raise RuntimeError("Verification is required before push")
        if self._pushed:
            return
        branch = self._branch or self._snapshot.branch  # type: ignore[union-attr]
        retries = max(1, self._policy.max_push_retries)
        last_err: Exception | None = None
        for _ in range(retries):
            try:
                await self._git("push", "--set-upstream", "origin", branch)
                self._pushed = True
                return
            except RuntimeError as exc:
                last_err = exc
        if last_err is not None:
            raise last_err

    async def create_pr(
        self,
        title: str,
        body: str,
        *,
        base: str = "main",
    ) -> str:
        if not self._pushed:
            raise RuntimeError("Cannot create PR before push")
        if self._policy.require_verification and not self._verified:
            raise RuntimeError("Verification is required before PR creation")
        if self._pr_url:
            return self._pr_url
        branch = self._branch or self._snapshot.branch  # type: ignore[union-attr]
        url = await self._run_cmd(
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            branch,
        )
        self._pr_url = url
        return url

    async def rollback(self) -> None:
        if self._pushed:
            raise RuntimeError("Cannot rollback after push")
        self._require_started()
        assert self._snapshot is not None
        await self._git("checkout", self._snapshot.branch)
        await self._git("reset", "--hard", self._snapshot.head_sha)
        self._committed = False
        self._branch = ""
        self._verified = False

    async def detect_external_changes(self) -> bool:
        self._require_started()
        assert self._snapshot is not None
        current = await self._git("rev-parse", "HEAD")
        return current != self._snapshot.head_sha

    def to_dict(self) -> dict[str, Any]:
        snap = self._snapshot
        return {
            "workspace": self._ws,
            "snapshot": (
                {
                    "branch": snap.branch,
                    "head_sha": snap.head_sha,
                    "is_dirty": snap.is_dirty,
                    "tracked_files": sorted(snap.tracked_files),
                }
                if snap
                else None
            ),
            "branch": self._branch,
            "committed": self._committed,
            "verified": self._verified,
            "pushed": self._pushed,
            "pr_url": self._pr_url,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        policy: TransactionPolicy | None = None,
    ) -> Self:
        obj = cls(data["workspace"], policy=policy)
        snap = data.get("snapshot")
        if snap:
            obj._snapshot = GitSnapshot(
                branch=snap["branch"],
                head_sha=snap["head_sha"],
                is_dirty=snap["is_dirty"],
                tracked_files=frozenset(snap["tracked_files"]),
            )
        obj._branch = data.get("branch", "")
        obj._committed = data.get("committed", False)
        obj._verified = data.get("verified", False)
        obj._pushed = data.get("pushed", False)
        obj._pr_url = data.get("pr_url", "")
        return obj

    def _require_started(self) -> None:
        if self._snapshot is None:
            raise RuntimeError("Transaction not started")

    async def _git(self, *args: str) -> str:
        return await self._run_cmd("git", *args)

    async def _run_cmd(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=self._ws,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"{args[0]} failed: {stderr.decode().strip()}")
        return stdout.decode().strip()
