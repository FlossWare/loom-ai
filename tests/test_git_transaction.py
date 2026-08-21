"""Tests for transactional Git operations."""

from __future__ import annotations

import subprocess

import pytest

from loom_ai.git_transaction import (
    GitSnapshot,
    GitTransaction,
    TransactionPolicy,
)


def _run_git(cwd: str, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _init_repo(tmp_path):
    cwd = str(tmp_path)
    _run_git(cwd, "init")
    _run_git(cwd, "config", "user.name", "Test")
    _run_git(cwd, "config", "user.email", "t@t.com")
    (tmp_path / "init.txt").write_text("init")
    _run_git(cwd, "add", "init.txt")
    _run_git(cwd, "commit", "-m", "initial")
    return cwd


@pytest.mark.asyncio
async def test_begin_captures_snapshot(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    snap = await tx.begin()
    assert isinstance(snap, GitSnapshot)
    assert snap.branch == "main" or snap.branch == "master"
    assert len(snap.head_sha) == 40
    assert snap.is_dirty is False
    assert isinstance(snap.tracked_files, frozenset)


@pytest.mark.asyncio
async def test_begin_fails_dirty_not_allowed(tmp_path):
    cwd = _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty")
    _run_git(cwd, "add", "dirty.txt")
    tx = GitTransaction(cwd)
    with pytest.raises(RuntimeError, match="dirty"):
        await tx.begin()


@pytest.mark.asyncio
async def test_begin_dirty_allowed(tmp_path):
    cwd = _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty")
    _run_git(cwd, "add", "dirty.txt")
    policy = TransactionPolicy(allow_dirty=True)
    tx = GitTransaction(cwd, policy=policy)
    snap = await tx.begin()
    assert snap.is_dirty is True
    assert "dirty.txt" in snap.tracked_files


@pytest.mark.asyncio
async def test_create_branch(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    name = await tx.create_branch("fix/test-822")
    assert name == "fix/test-822"
    branch = _run_git(
        cwd,
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
    )
    assert branch == "fix/test-822"


@pytest.mark.asyncio
async def test_stage_and_commit(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    await tx.create_branch("fix/commit-test")
    (tmp_path / "new.txt").write_text("content")
    sha = await tx.stage_and_commit(
        ["new.txt"],
        "test commit",
        author_name="Test Author",
        author_email="test@example.com",
    )
    assert len(sha) == 40
    log = _run_git(cwd, "log", "--oneline", "-1")
    assert "test commit" in log


@pytest.mark.asyncio
async def test_stage_and_commit_idempotent(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    (tmp_path / "f.txt").write_text("data")
    sha1 = await tx.stage_and_commit(
        ["f.txt"],
        "first",
        author_name="A",
        author_email="a@b.com",
    )
    sha2 = await tx.stage_and_commit(
        ["f.txt"],
        "second",
        author_name="A",
        author_email="a@b.com",
    )
    assert sha1 == sha2


@pytest.mark.asyncio
async def test_push_fails_not_committed(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    with pytest.raises(RuntimeError, match="Nothing"):
        await tx.push()


@pytest.mark.asyncio
async def test_rollback_restores(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    snap = await tx.begin()
    original_sha = snap.head_sha
    await tx.create_branch("fix/rollback-test")
    (tmp_path / "added.txt").write_text("x")
    await tx.stage_and_commit(
        ["added.txt"],
        "will rollback",
        author_name="T",
        author_email="t@t.com",
    )
    await tx.rollback()
    head = _run_git(cwd, "rev-parse", "HEAD")
    assert head == original_sha


@pytest.mark.asyncio
async def test_rollback_after_push_fails(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    tx._pushed = True
    with pytest.raises(RuntimeError, match="push"):
        await tx.rollback()


@pytest.mark.asyncio
async def test_detect_external_changes(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    assert await tx.detect_external_changes() is False
    (tmp_path / "ext.txt").write_text("external")
    _run_git(cwd, "add", "ext.txt")
    _run_git(cwd, "commit", "-m", "external change")
    assert await tx.detect_external_changes() is True


@pytest.mark.asyncio
async def test_to_dict_from_dict_roundtrip(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    d = tx.to_dict()
    tx2 = GitTransaction.from_dict(d)
    assert tx2._snapshot == tx._snapshot
    assert tx2._committed == tx._committed
    assert tx2._pushed == tx._pushed
    assert tx2._pr_url == tx._pr_url


def test_transaction_policy_defaults():
    p = TransactionPolicy()
    assert p.allow_dirty is False
    assert p.require_verification is True
    assert p.max_push_retries == 2
    assert p.max_pr_retries == 1


@pytest.mark.asyncio
async def test_begin_twice_raises(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    await tx.begin()
    with pytest.raises(RuntimeError, match="already"):
        await tx.begin()


@pytest.mark.asyncio
async def test_create_branch_before_begin(tmp_path):
    cwd = _init_repo(tmp_path)
    tx = GitTransaction(cwd)
    with pytest.raises(RuntimeError, match="not started"):
        await tx.create_branch("nope")


@pytest.mark.asyncio
async def test_snapshot_frozen():
    snap = GitSnapshot(
        branch="main",
        head_sha="a" * 40,
        is_dirty=False,
        tracked_files=frozenset(),
    )
    with pytest.raises(AttributeError):
        snap.branch = "other"
