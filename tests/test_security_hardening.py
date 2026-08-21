"""Security hardening tests for #779 and #797."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom_ai.backends.code_actions import _resolve_safe, validate_workspace
from loom_ai.demo_agent import DemoAgent


def _git_init(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
            "-q",
        ],
        cwd=path,
        check=True,
    )


class TestValidateWorkspace:
    def test_rejects_nonexistent(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            validate_workspace(str(tmp_path / "nope"))

    def test_rejects_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a directory"):
            validate_workspace(str(f))

    def test_rejects_no_git(self, tmp_path):
        d = tmp_path / "norepo"
        d.mkdir()
        with pytest.raises(ValueError, match="not a git repository"):
            validate_workspace(str(d))

    def test_rejects_symlink_workspace(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        _git_init(real)
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="symlink"):
            validate_workspace(str(link))

    def test_accepts_valid_workspace(self, tmp_path):
        ws = tmp_path / "repo"
        ws.mkdir()
        _git_init(ws)
        result = validate_workspace(str(ws))
        assert isinstance(result, Path)
        assert result == ws.resolve()


class TestResolveSafeSymlink:
    def test_rejects_symlink_component_escaping(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        (ws / "escape").symlink_to(outside)
        with pytest.raises(ValueError):
            _resolve_safe(ws, "escape/secret.txt")

    def test_allows_normal_paths(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "subdir").mkdir()
        (ws / "subdir" / "ok.txt").write_text("ok")
        result = _resolve_safe(ws, "subdir/ok.txt")
        assert result == (ws / "subdir" / "ok.txt").resolve()


class TestDispatchAutoPr:
    def test_auto_pr_defaults_false(self, tmp_path):
        _git_init(tmp_path)
        from loom_ai.mcp_server import _dispatch_resolve_issue

        with (
            patch(
                "loom_ai.backends.code_actions.validate_workspace",
                return_value=tmp_path,
            ),
            patch(
                "loom_ai.demo_agent.DemoAgent.create",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            mock_agent = AsyncMock()
            mock_agent.run.return_value = MagicMock(
                success=True, error="", plan="", pr_url=""
            )
            mock_create.return_value = mock_agent
            _dispatch_resolve_issue(
                {
                    "issue_number": 1,
                    "issue_text": "test",
                    "workspace": str(tmp_path),
                }
            )
            mock_agent.run.assert_awaited_once()
            call_kwargs = mock_agent.run.call_args
            assert (
                call_kwargs.kwargs.get("auto_pr") is False
                or call_kwargs[1].get("auto_pr") is False
            )


class TestBranchCollision:
    async def test_uses_suffix_on_collision(self, tmp_path):
        _git_init(tmp_path)
        llm = MagicMock()
        agent = DemoAgent(llm=llm, workspace=str(tmp_path))

        git_calls = []

        async def mock_git(*args, cwd):
            git_calls.append(args)
            if args == ("branch", "--list", "fix/issue-42"):
                return "  fix/issue-42"
            if args == ("branch", "--list", "fix/issue-42-2"):
                return ""
            return ""

        with patch("loom_ai.demo_agent._git", side_effect=mock_git):
            with patch("asyncio.create_subprocess_exec") as mock_proc:
                proc = AsyncMock()
                proc.communicate.return_value = (
                    b"https://github.com/test/pull/1\n",
                    b"",
                )
                proc.returncode = 0
                mock_proc.return_value = proc
                await agent._commit_and_pr(42, ["test.py"])

        checkout_calls = [c for c in git_calls if c[0] == "checkout"]
        assert any("fix/issue-42-2" in c for c in checkout_calls)
