"""Tests for the InMemoryBudgetTracker backend."""

from loom_ai.backends.budget import InMemoryBudgetTracker, _extract_provider
from loom_ai.contracts_phase2 import BudgetTracker
from loom_ai.models_phase2 import TokenUsage

# -- protocol conformance ---------------------------------------------------


def test_satisfies_protocol():
    """InMemoryBudgetTracker must be recognised as a BudgetTracker."""
    tracker = InMemoryBudgetTracker()
    assert isinstance(tracker, BudgetTracker)


# -- record_usage -----------------------------------------------------------


async def test_record_usage_accumulates_tokens():
    tracker = InMemoryBudgetTracker()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    await tracker.record_usage("gpt-4o", usage)

    status = await tracker.remaining()
    assert status.tokens_used == 150


async def test_record_usage_accumulates_across_calls():
    tracker = InMemoryBudgetTracker()
    u1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    u2 = TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
    await tracker.record_usage("gpt-4o", u1)
    await tracker.record_usage("gpt-4o", u2)

    status = await tracker.remaining()
    assert status.tokens_used == 450


async def test_record_usage_default_cost():
    """Default rate is 0.01 per 1k tokens."""
    tracker = InMemoryBudgetTracker()
    usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("some-model", usage)

    status = await tracker.remaining()
    assert status.cost_used == 0.01  # 1000 * 0.01 / 1000


async def test_record_usage_custom_model_rate():
    tracker = InMemoryBudgetTracker(model_rates={"expensive": 0.10})
    usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("expensive", usage)

    status = await tracker.remaining()
    assert status.cost_used == 0.10  # 1000 * 0.10 / 1000


async def test_record_usage_custom_default_rate():
    tracker = InMemoryBudgetTracker(default_rate=0.05)
    usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=2000)
    await tracker.record_usage("any-model", usage)

    status = await tracker.remaining()
    assert status.cost_used == 0.10  # 2000 * 0.05 / 1000


async def test_record_usage_with_task_id():
    tracker = InMemoryBudgetTracker()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=100, total_tokens=200)
    await tracker.record_usage("m", usage, task_id="task-1")

    report = await tracker.cost_report()
    assert "task-1" in report.by_task
    assert report.by_task["task-1"] > 0


async def test_record_usage_without_task_id():
    tracker = InMemoryBudgetTracker()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=100, total_tokens=200)
    await tracker.record_usage("m", usage)

    report = await tracker.cost_report()
    assert report.by_task == {}


# -- remaining ---------------------------------------------------------------


async def test_remaining_no_budget_set():
    """When no budget is set, remaining fields are None."""
    tracker = InMemoryBudgetTracker()
    status = await tracker.remaining()
    assert status.tokens_used == 0
    assert status.tokens_remaining is None
    assert status.cost_used == 0.0
    assert status.cost_remaining is None


async def test_remaining_with_token_budget():
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_tokens=1000)
    usage = TokenUsage(prompt_tokens=100, completion_tokens=100, total_tokens=200)
    await tracker.record_usage("m", usage)

    status = await tracker.remaining()
    assert status.tokens_used == 200
    assert status.tokens_remaining == 800


async def test_remaining_with_cost_budget():
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_cost=1.0)
    # Use 1000 tokens at default 0.01/1k = $0.01
    usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("m", usage)

    status = await tracker.remaining()
    assert abs(status.cost_used - 0.01) < 1e-9
    assert status.cost_remaining is not None
    assert abs(status.cost_remaining - 0.99) < 1e-9


async def test_remaining_floors_at_zero():
    """Remaining never goes negative, even when budget is exceeded."""
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_tokens=100, max_cost=0.001)
    usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("m", usage)

    status = await tracker.remaining()
    assert status.tokens_remaining == 0
    assert status.cost_remaining == 0.0


# -- set_budget --------------------------------------------------------------


async def test_set_budget_tokens_only():
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_tokens=5000)

    status = await tracker.remaining()
    assert status.tokens_remaining == 5000
    assert status.cost_remaining is None


async def test_set_budget_cost_only():
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_cost=10.0)

    status = await tracker.remaining()
    assert status.tokens_remaining is None
    assert status.cost_remaining == 10.0


async def test_set_budget_both():
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_tokens=5000, max_cost=10.0)

    status = await tracker.remaining()
    assert status.tokens_remaining == 5000
    assert status.cost_remaining == 10.0


async def test_set_budget_update_preserves_other():
    """Updating one limit does not reset the other."""
    tracker = InMemoryBudgetTracker()
    await tracker.set_budget(max_tokens=5000, max_cost=10.0)
    await tracker.set_budget(max_tokens=8000)

    status = await tracker.remaining()
    assert status.tokens_remaining == 8000
    assert status.cost_remaining == 10.0


# -- cost_report -------------------------------------------------------------


async def test_cost_report_empty():
    tracker = InMemoryBudgetTracker()
    report = await tracker.cost_report()
    assert report.total_cost == 0.0
    assert report.by_model == {}
    assert report.by_provider == {}
    assert report.by_task == {}


async def test_cost_report_by_model():
    tracker = InMemoryBudgetTracker()
    u1 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    u2 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("model-a", u1)
    await tracker.record_usage("model-b", u2)

    report = await tracker.cost_report()
    assert "model-a" in report.by_model
    assert "model-b" in report.by_model
    assert (
        abs(
            report.total_cost
            - (report.by_model["model-a"] + report.by_model["model-b"])
        )
        < 1e-9
    )


async def test_cost_report_by_provider_slash():
    """Models with ``provider/name`` format group under provider."""
    tracker = InMemoryBudgetTracker()
    u1 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    u2 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("openai/gpt-4o", u1)
    await tracker.record_usage("openai/gpt-3.5-turbo", u2)

    report = await tracker.cost_report()
    assert "openai" in report.by_provider
    assert abs(report.by_provider["openai"] - report.total_cost) < 1e-9


async def test_cost_report_by_provider_no_slash():
    """Models without ``/`` use the full name as provider."""
    tracker = InMemoryBudgetTracker()
    usage = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("claude-sonnet", usage)

    report = await tracker.cost_report()
    assert "claude-sonnet" in report.by_provider


async def test_cost_report_by_task():
    tracker = InMemoryBudgetTracker()
    u1 = TokenUsage(prompt_tokens=250, completion_tokens=250, total_tokens=500)
    u2 = TokenUsage(prompt_tokens=250, completion_tokens=250, total_tokens=500)
    u3 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("m", u1, task_id="task-alpha")
    await tracker.record_usage("m", u2, task_id="task-alpha")
    await tracker.record_usage("m", u3, task_id="task-beta")

    report = await tracker.cost_report()
    assert "task-alpha" in report.by_task
    assert "task-beta" in report.by_task
    # task-alpha: 500+500 = 1000 tokens, task-beta: 1000 tokens
    assert abs(report.by_task["task-alpha"] - report.by_task["task-beta"]) < 1e-9


async def test_cost_report_multiple_providers():
    tracker = InMemoryBudgetTracker(
        model_rates={"openai/gpt-4o": 0.03, "google/gemini-pro": 0.005}
    )
    u1 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    u2 = TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000)
    await tracker.record_usage("openai/gpt-4o", u1)
    await tracker.record_usage("google/gemini-pro", u2)

    report = await tracker.cost_report()
    assert "openai" in report.by_provider
    assert "google" in report.by_provider
    assert abs(report.by_provider["openai"] - 0.03) < 1e-9
    assert abs(report.by_provider["google"] - 0.005) < 1e-9


# -- _extract_provider -------------------------------------------------------


def test_extract_provider_with_slash():
    assert _extract_provider("openai/gpt-4o") == "openai"
    assert _extract_provider("google/gemini-pro") == "google"
    assert _extract_provider("anthropic/claude-3") == "anthropic"


def test_extract_provider_without_slash():
    assert _extract_provider("gpt-4o") == "gpt-4o"
    assert _extract_provider("claude-sonnet") == "claude-sonnet"


def test_extract_provider_multiple_slashes():
    assert _extract_provider("a/b/c") == "a"
