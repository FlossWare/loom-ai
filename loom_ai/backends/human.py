"""Human-in-the-loop backend implementations for loom-ai.

Provides two concrete implementations of the
:class:`~loom_ai.contracts_phase3.HumanInTheLoop` protocol:

CallbackHumanInTheLoop   -- delegates to caller-supplied callbacks
AutoApproveHumanInTheLoop -- always approves (for testing / CI pipelines)

All classes use only the standard library -- zero external dependencies.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable


class CallbackHumanInTheLoop:
    """Human-in-the-loop backend driven by caller-supplied callbacks.

    Satisfies :class:`~loom_ai.contracts_phase3.HumanInTheLoop` via
    structural subtyping.

    Parameters
    ----------
    input_handler:
        A callable ``(prompt, options) -> response``.  May be sync or async.
    notify_handler:
        An optional callable ``(message) -> None``.  May be sync or async.
        When ``None``, :meth:`notify` is a silent no-op.
    """

    def __init__(
        self,
        input_handler: Callable[..., Any],
        notify_handler: Callable[..., Any] | None = None,
    ) -> None:
        self._input_handler = input_handler
        self._notify_handler = notify_handler

    async def request_input(
        self,
        prompt: str,
        *,
        options: list[str] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Present *prompt* to the human via the input callback.

        If *timeout* is given, raises :class:`asyncio.TimeoutError` when
        the callback does not return in time.  When *options* is
        provided the response is validated against the list; a
        ``ValueError`` is raised for responses not in *options*.
        """

        async def _call() -> str:
            result = self._input_handler(prompt, options)
            if inspect.isawaitable(result):
                result = await result
            return str(result)

        if timeout is not None:
            response = await asyncio.wait_for(_call(), timeout=timeout)
        else:
            response = await _call()

        if options is not None and response not in options:
            raise ValueError(
                f"Response {response!r} is not in the allowed options: {options}"
            )

        return response

    async def notify(self, message: str) -> None:
        """Forward *message* to the notify callback, if one was provided."""
        if self._notify_handler is None:
            return
        result = self._notify_handler(message)
        if inspect.isawaitable(result):
            await result


class AutoApproveHumanInTheLoop:
    """Human-in-the-loop backend that always approves automatically.

    Useful for testing, CI pipelines, and non-interactive deployments
    where human intervention is not available.

    Satisfies :class:`~loom_ai.contracts_phase3.HumanInTheLoop` via
    structural subtyping.

    Behaviour
    ---------
    - ``request_input`` returns the first element of *options* when
      provided, otherwise the string ``"approved"``.
    - ``notify`` is a silent no-op.
    """

    async def request_input(
        self,
        _prompt: str,
        *,
        options: list[str] | None = None,
        _timeout: float | None = None,
    ) -> str:
        """Return the first option or ``"approved"``."""
        if options:
            return options[0]
        return "approved"

    async def notify(self, message: str) -> None:
        """No-op -- nothing to notify in auto-approve mode."""
