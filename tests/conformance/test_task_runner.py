"""Conformance tests for TaskRunner implementations.

Any backend that satisfies the TaskRunner protocol should pass all
tests in this module.  Override the ``task_runner`` and ``loom_config``
fixtures in a downstream ``conftest.py`` to plug in a different
implementation.
"""

from __future__ import annotations

from loom_ai.models import Task


async def test_run_task_returns_result(task_runner, loom_config):
    """run() returns a result for a valid task."""
    task = Task(
        id="t-1",
        name="greet",
        description="Say hello",
        input_data={"greeting": "hello"},
    )

    result = await task_runner.run(task, loom_config)

    assert result is not None


async def test_run_task_passes_through_input(task_runner, loom_config):
    """The NoopTaskRunner passes input_data through as the result."""
    payload = {"key": "value", "number": 42}
    task = Task(
        id="t-2",
        name="passthrough",
        description="Echo input",
        input_data=payload,
    )

    result = await task_runner.run(task, loom_config)

    assert result == payload


async def test_run_task_empty_input(task_runner, loom_config):
    """Running a task with empty input_data still returns a result."""
    task = Task(id="t-3", name="empty", description="No input")

    result = await task_runner.run(task, loom_config)

    assert result is not None
    assert isinstance(result, dict)
