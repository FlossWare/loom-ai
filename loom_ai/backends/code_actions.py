"""Code-action MCP tools for autonomous code modification.

Provides tools for applying diffs, running linters, formatting code,
executing tests, and staging changes.  Registers as a
:class:`~loom_ai.backends.memory_mcp.MemoryToolProvider` so any
MCP-compatible client can use these tools.

All file operations are sandboxed to a configurable workspace root
(defaults to cwd).  Paths outside the workspace are rejected.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

from loom_ai.backends.memory_mcp import MemoryToolProvider
from loom_ai.models import ToolDefinition


def _resolve_safe(workspace: Path, relpath: str) -> Path:
    """Resolve *relpath* under *workspace*, rejecting escapes."""
    target = (workspace / relpath).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise ValueError(f"Path escapes workspace: {relpath}")
    return target


async def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    """Run a subprocess and return stdout, stderr, and exit code."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}
    return {
        "exit_code": proc.returncode,
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
    }


async def apply_diff(
    file: str,
    search: str,
    replace: str,
    *,
    workspace: str = "",
) -> dict[str, Any]:
    """Apply a search-and-replace block to a file."""
    ws = Path(workspace or os.getcwd())
    target = _resolve_safe(ws, file)
    if not target.is_file():
        return {"applied": False, "error": f"File not found: {file}"}

    content = target.read_text()
    if search not in content:
        return {"applied": False, "error": "Search text not found in file"}

    count = content.count(search)
    if count > 1:
        return {
            "applied": False,
            "error": f"Search text is ambiguous ({count} occurrences)",
        }

    new_content = content.replace(search, replace, 1)
    target.write_text(new_content)
    return {
        "applied": True,
        "file": file,
        "checksum": hashlib.sha256(new_content.encode()).hexdigest()[:16],
    }


async def run_linter(
    path: str = ".",
    *,
    tool: str = "ruff",
    workspace: str = "",
) -> dict[str, Any]:
    """Run a linter on a file or directory."""
    ws = Path(workspace or os.getcwd())
    target = _resolve_safe(ws, path)

    if tool == "ruff":
        cmd = ["ruff", "check", str(target)]
    elif tool == "mypy":
        cmd = ["mypy", str(target)]
    elif tool == "flake8":
        cmd = ["flake8", str(target)]
    else:
        return {"error": f"Unknown linter: {tool}"}

    if not shutil.which(cmd[0]):
        return {"error": f"{cmd[0]} not found in PATH"}

    result = await _run(cmd, ws)
    findings = []
    for line in result["stdout"].splitlines():
        match = re.match(r"^(.+):(\d+):(\d+):\s+(\S+)\s+(.*)", line)
        if match:
            findings.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "col": int(match.group(3)),
                "code": match.group(4),
                "message": match.group(5),
            })
    return {
        "tool": tool,
        "exit_code": result["exit_code"],
        "findings": findings,
        "count": len(findings),
        "raw": result["stdout"][:4000],
    }


async def format_code(
    path: str = ".",
    *,
    tool: str = "ruff",
    workspace: str = "",
) -> dict[str, Any]:
    """Run a code formatter on modified files."""
    ws = Path(workspace or os.getcwd())
    target = _resolve_safe(ws, path)

    if tool == "ruff":
        cmd = ["ruff", "format", str(target)]
    elif tool == "black":
        cmd = ["black", str(target)]
    else:
        return {"error": f"Unknown formatter: {tool}"}

    if not shutil.which(cmd[0]):
        return {"error": f"{cmd[0]} not found in PATH"}

    result = await _run(cmd, ws)
    return {
        "formatted": result["exit_code"] == 0,
        "tool": tool,
        "output": result["stdout"][:4000],
    }


async def run_tests(
    path: str = "tests/",
    *,
    pattern: str = "",
    workspace: str = "",
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute pytest on specified tests."""
    ws = Path(workspace or os.getcwd())
    _resolve_safe(ws, path)

    cmd = ["python", "-m", "pytest", path, "-x", "-q", "--tb=short"]
    if pattern:
        cmd.extend(["-k", pattern])

    if not shutil.which("python"):
        return {"error": "python not found in PATH"}

    result = await _run(cmd, ws, timeout=timeout)
    passed = failed = 0
    for line in result["stdout"].splitlines():
        match = re.match(r"(\d+) passed", line)
        if match:
            passed = int(match.group(1))
        match = re.match(r"(\d+) failed", line)
        if match:
            failed = int(match.group(1))
    return {
        "exit_code": result["exit_code"],
        "passed": passed,
        "failed": failed,
        "output": result["stdout"][-4000:],
    }


async def validate_change(
    file: str,
    search: str,
    replace: str,
    *,
    test_path: str = "tests/",
    workspace: str = "",
) -> dict[str, Any]:
    """Composite: apply diff, lint, test, report."""
    apply_result = await apply_diff(file, search, replace, workspace=workspace)
    if not apply_result.get("applied"):
        return {"validated": False, "stage": "apply", "error": apply_result}

    lint_result = await run_linter(file, workspace=workspace)
    if lint_result.get("exit_code", 1) != 0:
        return {
            "validated": False,
            "stage": "lint",
            "apply": apply_result,
            "lint": lint_result,
        }

    test_result = await run_tests(test_path, workspace=workspace)
    return {
        "validated": test_result.get("exit_code") == 0,
        "apply": apply_result,
        "lint": lint_result,
        "test": test_result,
    }


async def git_stage(
    files: list[str] | None = None,
    *,
    workspace: str = "",
) -> dict[str, Any]:
    """Stage validated changes for commit."""
    ws = Path(workspace or os.getcwd())
    cmd = ["git", "add"]
    if files:
        for f in files:
            _resolve_safe(ws, f)
        cmd.extend(files)
    else:
        cmd.append("-u")
    result = await _run(cmd, ws)
    return {
        "staged": result["exit_code"] == 0,
        "files": files or ["(tracked changes)"],
        "error": result["stderr"] if result["exit_code"] != 0 else None,
    }


_TOOL_DEFS = [
    ToolDefinition(
        name="apply_diff",
        description="Apply a search-and-replace block to a file",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Relative file path"},
                "search": {
                    "type": "string",
                    "description": "Text to find (must be unique)",
                },
                "replace": {
                    "type": "string",
                    "description": "Replacement text",
                },
                "workspace": {
                    "type": "string",
                    "description": "Workspace root (default: cwd)",
                },
            },
            "required": ["file", "search", "replace"],
        },
    ),
    ToolDefinition(
        name="run_linter",
        description="Run ruff/flake8/mypy on a file or directory",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory to lint"},
                "tool": {"type": "string", "enum": ["ruff", "mypy", "flake8"]},
                "workspace": {"type": "string"},
            },
        },
    ),
    ToolDefinition(
        name="format_code",
        description="Run ruff format or black on files",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory to format",
                },
                "tool": {"type": "string", "enum": ["ruff", "black"]},
                "workspace": {"type": "string"},
            },
        },
    ),
    ToolDefinition(
        name="run_tests",
        description="Execute pytest on specified tests",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Test path"},
                "pattern": {"type": "string", "description": "pytest -k pattern"},
                "workspace": {"type": "string"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
            },
        },
    ),
    ToolDefinition(
        name="validate_change",
        description="Apply diff, lint, and test in one step",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "search": {"type": "string"},
                "replace": {"type": "string"},
                "test_path": {"type": "string"},
                "workspace": {"type": "string"},
            },
            "required": ["file", "search", "replace"],
        },
    ),
    ToolDefinition(
        name="git_stage",
        description="Stage validated changes for commit",
        input_schema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to stage (default: tracked changes)",
                },
                "workspace": {"type": "string"},
            },
        },
    ),
]

_HANDLERS = {
    "apply_diff": apply_diff,
    "run_linter": run_linter,
    "format_code": format_code,
    "run_tests": run_tests,
    "validate_change": validate_change,
    "git_stage": git_stage,
}


def create_code_action_provider(
    workspace: str | None = None,
) -> MemoryToolProvider:
    """Create a MemoryToolProvider pre-loaded with code-action tools."""
    provider = MemoryToolProvider()
    for defn in _TOOL_DEFS:
        provider.register(defn, _HANDLERS[defn.name])
    return provider
