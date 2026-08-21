from __future__ import annotations

import subprocess

import pytest

from loom_ai.git_transaction import GitTransaction


def _git(cwd: str, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(tmp_path) -> str:
    cwd = str(tmp_path)
    _git(cwd, "init")
    _git(cwd, "config", "user.name", "Test")
    _git(cwd, "config", "user.email", "test@example.com")
    (tmp_path / "init.txt").write_text("init")
    _git(cwd, "add", "init.txt")
    _git(cwd, "commit", "-m", "initial")
    return cwd


@pytest.mark.asyncio
async def test_push_requires_verification(tmp_path):
    cwd = _repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    await tx.create_branch("fix/verification")
    (tmp_path / "change.txt").write_text("change")
    await tx.stage_and_commit(
        ["change.txt"], "change", author_name="Test", author_email="test@example.com"
    )
    with pytest.raises(RuntimeError, match="Verification is required"):
        await tx.push()


@pytest.mark.asyncio
async def test_mark_verified_allows_publication_attempt(tmp_path):
    cwd = _repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    await tx.create_branch("fix/verified")
    (tmp_path / "change.txt").write_text("change")
    await tx.stage_and_commit(
        ["change.txt"], "change", author_name="Test", author_email="test@example.com"
    )
    tx.mark_verified()
    with pytest.raises(RuntimeError):
        await tx.push()
    assert tx.to_dict()["verified"] is True
