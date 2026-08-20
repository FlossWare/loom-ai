"""Tests for human-in-the-loop backends: CallbackHumanInTheLoop and
AutoApproveHumanInTheLoop.

Covers callback invocation, timeout handling, option validation,
auto-approve behaviour, and notify forwarding.  No external
dependencies required.
"""

import asyncio

import pytest

from loom_ai.backends.human import (
    AutoApproveHumanInTheLoop,
    CallbackHumanInTheLoop,
)

# ── CallbackHumanInTheLoop ──────────────────────────────────────────────


async def test_callback_sync_input_handler():
    """A synchronous input handler is called with prompt and options."""
    calls: list[tuple] = []

    def handler(prompt, options):
        calls.append((prompt, options))
        return "yes"

    hitl = CallbackHumanInTheLoop(input_handler=handler)
    result = await hitl.request_input("Continue?", options=["yes", "no"])

    assert result == "yes"
    assert calls == [("Continue?", ["yes", "no"])]


async def test_callback_async_input_handler():
    """An async input handler is awaited correctly."""

    async def handler(prompt, options):
        return "go"

    hitl = CallbackHumanInTheLoop(input_handler=handler)
    result = await hitl.request_input("Action?", options=["go", "stop"])

    assert result == "go"


async def test_callback_no_options():
    """When options is None the handler receives None and no validation."""
    received_options = []

    def handler(prompt, options):
        received_options.append(options)
        return "anything"

    hitl = CallbackHumanInTheLoop(input_handler=handler)
    result = await hitl.request_input("Say something")

    assert result == "anything"
    assert received_options == [None]


async def test_callback_option_validation_rejects_bad_response():
    """A response not in options raises ValueError."""

    def handler(prompt, options):
        return "maybe"

    hitl = CallbackHumanInTheLoop(input_handler=handler)

    with pytest.raises(ValueError, match="not in the allowed options"):
        await hitl.request_input("Pick one", options=["yes", "no"])


async def test_callback_option_validation_passes_good_response():
    """A response that is in options passes validation."""

    def handler(prompt, options):
        return "no"

    hitl = CallbackHumanInTheLoop(input_handler=handler)
    result = await hitl.request_input("Pick one", options=["yes", "no"])

    assert result == "no"


async def test_callback_timeout_raises():
    """A slow handler triggers asyncio.TimeoutError when timeout is set."""

    async def slow_handler(prompt, options):
        await asyncio.sleep(60)
        return "late"

    hitl = CallbackHumanInTheLoop(input_handler=slow_handler)

    with pytest.raises(asyncio.TimeoutError):
        await hitl.request_input("Hurry", timeout=0.05)


async def test_callback_timeout_not_exceeded():
    """A fast handler completes within the timeout window."""

    async def fast_handler(prompt, options):
        return "quick"

    hitl = CallbackHumanInTheLoop(input_handler=fast_handler)
    result = await hitl.request_input("Go", timeout=5.0)

    assert result == "quick"


async def test_callback_notify_sync():
    """A synchronous notify handler is called correctly."""
    messages: list[str] = []

    def notifier(message):
        messages.append(message)

    hitl = CallbackHumanInTheLoop(
        input_handler=lambda p, o: "ok", notify_handler=notifier
    )
    await hitl.notify("Hello operator")

    assert messages == ["Hello operator"]


async def test_callback_notify_async():
    """An async notify handler is awaited correctly."""
    messages: list[str] = []

    async def notifier(message):
        messages.append(message)

    hitl = CallbackHumanInTheLoop(
        input_handler=lambda p, o: "ok", notify_handler=notifier
    )
    await hitl.notify("Async hello")

    assert messages == ["Async hello"]


async def test_callback_notify_none_is_noop():
    """When no notify_handler is provided, notify is a silent no-op."""
    hitl = CallbackHumanInTheLoop(input_handler=lambda p, o: "ok")
    # Should not raise
    await hitl.notify("This goes nowhere")


async def test_callback_coerces_to_string():
    """Non-string return values are coerced to str."""

    def handler(prompt, options):
        return 42

    hitl = CallbackHumanInTheLoop(input_handler=handler)
    result = await hitl.request_input("Number?")

    assert result == "42"
    assert isinstance(result, str)


# ── AutoApproveHumanInTheLoop ───────────────────────────────────────────


async def test_auto_approve_returns_first_option():
    """With options provided, auto-approve returns the first one."""
    hitl = AutoApproveHumanInTheLoop()
    result = await hitl.request_input("Approve?", options=["yes", "no"])

    assert result == "yes"


async def test_auto_approve_returns_approved_without_options():
    """Without options, auto-approve returns 'approved'."""
    hitl = AutoApproveHumanInTheLoop()
    result = await hitl.request_input("Approve?")

    assert result == "approved"


async def test_auto_approve_returns_approved_for_empty_options():
    """With an empty options list, auto-approve returns 'approved'."""
    hitl = AutoApproveHumanInTheLoop()
    result = await hitl.request_input("Approve?", options=[])

    assert result == "approved"


async def test_auto_approve_ignores_timeout():
    """Timeout parameter is accepted but has no effect."""
    hitl = AutoApproveHumanInTheLoop()
    result = await hitl.request_input("Approve?", options=["go"], timeout=0.001)

    assert result == "go"


async def test_auto_approve_notify_is_noop():
    """notify is a silent no-op on AutoApproveHumanInTheLoop."""
    hitl = AutoApproveHumanInTheLoop()
    # Should not raise
    await hitl.notify("Ignored")


# ── Protocol conformance ────────────────────────────────────────────────


async def test_callback_satisfies_protocol():
    """CallbackHumanInTheLoop is recognized by the runtime_checkable protocol."""
    from loom_ai.contracts_session import HumanInTheLoop

    hitl = CallbackHumanInTheLoop(input_handler=lambda p, o: "ok")
    assert isinstance(hitl, HumanInTheLoop)


async def test_auto_approve_satisfies_protocol():
    """AutoApproveHumanInTheLoop is recognized by the runtime_checkable protocol."""
    from loom_ai.contracts_session import HumanInTheLoop

    hitl = AutoApproveHumanInTheLoop()
    assert isinstance(hitl, HumanInTheLoop)
