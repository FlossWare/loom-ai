"""Tests for code-action MCP tools (#721)."""

from __future__ import annotations

import os

import pytest

from loom_ai.backends.code_actions import (
    apply_diff,
    create_code_action_provider,
    format_code,
    git_stage,
    run_linter,
    run_tests,
    validate_change,
)


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace with a sample Python file."""
    sample = tmp_path / "sample.py"
    sample.write_text('def hello():\n    return "world"\n')
    return tmp_path


class TestApplyDiff:
    async def test_applies_replacement(self, workspace):
        result = await apply_diff(
            "sample.py",
            '"world"',
            '"earth"',
            workspace=str(workspace),
        )
        assert result["applied"] is True
        content = (workspace / "sample.py").read_text()
        assert '"earth"' in content

    async def test_rejects_missing_file(self, workspace):
        result = await apply_diff(
            "missing.py",
            "x",
            "y",
            workspace=str(workspace),
        )
        assert result["applied"] is False
        assert "not found" in result["error"]

    async def test_rejects_missing_search_text(self, workspace):
        result = await apply_diff(
            "sample.py",
            "nonexistent",
            "y",
            workspace=str(workspace),
        )
        assert result["applied"] is False
        assert "not found" in result["error"]

    async def test_rejects_ambiguous_match(self, workspace):
        f = workspace / "dup.py"
        f.write_text("x = 1\ny = 1\n")
        result = await apply_diff("dup.py", "1", "2", workspace=str(workspace))
        assert result["applied"] is False
        assert "ambiguous" in result["error"]

    async def test_rejects_path_traversal(self, workspace):
        with pytest.raises(ValueError, match="escapes"):
            await apply_diff(
                "../../../etc/passwd",
                "x",
                "y",
                workspace=str(workspace),
            )


class TestRunLinter:
    async def test_ruff_on_clean_file(self, workspace):
        result = await run_linter("sample.py", workspace=str(workspace))
        assert result["tool"] == "ruff"
        assert isinstance(result["findings"], list)

    async def test_unknown_linter(self, workspace):
        result = await run_linter("sample.py", tool="unknown", workspace=str(workspace))
        assert "error" in result


class TestFormatCode:
    async def test_ruff_format(self, workspace):
        result = await format_code("sample.py", workspace=str(workspace))
        assert result["tool"] == "ruff"

    async def test_unknown_formatter(self, workspace):
        result = await format_code(
            "sample.py",
            tool="unknown",
            workspace=str(workspace),
        )
        assert "error" in result


class TestRunTests:
    async def test_runs_pytest(self, workspace):
        test_file = workspace / "test_hello.py"
        test_file.write_text("def test_one(): assert 1 + 1 == 2\n")
        result = await run_tests("test_hello.py", workspace=str(workspace))
        assert result["exit_code"] == 0
        assert result["passed"] >= 1


class TestValidateChange:
    async def test_validates_good_change(self, workspace):
        test_file = workspace / "test_hello.py"
        test_file.write_text("def test_one(): assert 1 + 1 == 2\n")
        result = await validate_change(
            "sample.py",
            '"world"',
            '"earth"',
            test_path="test_hello.py",
            workspace=str(workspace),
        )
        assert result["apply"]["applied"] is True

    async def test_fails_on_bad_diff(self, workspace):
        result = await validate_change(
            "sample.py",
            "nonexistent",
            "y",
            workspace=str(workspace),
        )
        assert result["validated"] is False
        assert result["stage"] == "apply"


class TestGitStage:
    async def test_stages_in_git_repo(self, workspace):
        os.system(f"git -C {workspace} init -q")
        os.system(f"git -C {workspace} add sample.py")
        os.system(
            f"git -C {workspace} -c user.name=test -c user.email=t@t commit -m init -q",
        )
        (workspace / "sample.py").write_text("# changed\n")
        result = await git_stage(["sample.py"], workspace=str(workspace))
        assert result["staged"] is True


class TestProvider:
    def test_creates_provider_with_all_tools(self):
        provider = create_code_action_provider()
        import asyncio

        tools = asyncio.run(provider.list_tools())
        names = {t.name for t in tools}
        assert "apply_diff" in names
        assert "run_linter" in names
        assert "format_code" in names
        assert "run_tests" in names
        assert "validate_change" in names
        assert "git_stage" in names
