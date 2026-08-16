"""Provider-agnostic multi-model consensus engine.

Extracted from ``HttpLLMBackend.consensus()`` (issue #3) into a
first-class orchestration component that works with any ``LLMBackend``.

Features
--------
- Fan-out to N models with deadline-based timeouts
- ``asyncio.Semaphore`` concurrency limiting
- Exponential backoff with jitter on retryable errors
- Graceful partial-failure handling (returns whatever succeeds)
- Arbiter synthesis via prompts from ``loom_ai.prompts``
- Extensible: subclass or compose for weighted voting, Thompson
  Sampling, adversarial verification, etc.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.prompts import build_arbiter_messages, build_worker_messages

if TYPE_CHECKING:
    from loom_ai.protocols import LLMBackend


@dataclass
class ConsensusResult:
    """Outcome of a full consensus round (gather + arbiter synthesis).

    ``arbiter_attempted`` distinguishes a successful synthesis from the
    case where there were no worker responses and synthesis was never
    attempted.  ``arbiter_error`` is populated when the arbiter was
    attempted but failed after the configured retry/deadline policy.
    """

    synthesis: ChatResponse
    worker_responses: list[ChatResponse] = field(default_factory=list)
    failed_models: list[str] = field(default_factory=list)
    arbiter_attempted: bool = False
    arbiter_error: str | None = None


class ConsensusEngine:
    """Provider-agnostic multi-model consensus with arbiter synthesis.

    Takes any :class:`~loom_ai.protocols.LLMBackend` and fans out
    queries to multiple models, handling retries, timeouts, and
    concurrency.  Optionally synthesises a single response via an
    arbiter model.

    Parameters
    ----------
    backend:
        Any object satisfying the ``LLMBackend`` protocol.
    max_concurrent:
        Maximum number of in-flight model calls (semaphore width).
    timeout_seconds:
        Hard deadline for the entire fan-out phase and each arbiter call.
    retries:
        Per-model retry count on retryable errors (429, 5xx, timeout).
    """

    def __init__(
        self,
        backend: LLMBackend,
        *,
        max_concurrent: int = 10,
        timeout_seconds: int = 60,
        retries: int = 2,
    ) -> None:
        self._backend = backend
        self._max_concurrent = max_concurrent
        self._timeout_seconds = timeout_seconds
        self._retries = retries

    async def gather(
        self,
        messages: list[ChatMessage],
        models: list[str],
        *,
        temperature: float = 0.7,
        max_concurrent: int | None = None,
        timeout_seconds: int | None = None,
        retries: int | None = None,
    ) -> tuple[list[ChatResponse], list[str]]:
        """Fan out *messages* to *models* and collect responses.

        Returns a ``(responses, failed_models)`` tuple.  Responses are
        only for models that succeeded; failed models are listed
        separately so callers can decide how to handle partial failure.
        """
        sem = asyncio.Semaphore(
            max_concurrent or self._max_concurrent,
        )
        deadline = time.monotonic() + (
            timeout_seconds if timeout_seconds is not None else self._timeout_seconds
        )
        max_retries = retries if retries is not None else self._retries

        async def _worker(
            model_id: str,
        ) -> tuple[ChatResponse | None, str]:
            for attempt in range(1 + max_retries):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    async with sem:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        resp = await asyncio.wait_for(
                            self._backend.chat(
                                messages,
                                model=model_id,
                                temperature=temperature,
                            ),
                            timeout=remaining,
                        )
                        return resp, model_id
                except Exception as exc:
                    if not self._is_retryable(exc):
                        break
                    delay = min(
                        (2**attempt) + random.uniform(0, 1),
                        max(0, deadline - time.monotonic()),
                    )
                    if attempt < max_retries and delay > 0:
                        await asyncio.sleep(delay)
            return None, model_id

        tasks = [_worker(m) for m in models]
        raw = await asyncio.gather(*tasks)

        responses: list[ChatResponse] = []
        failed: list[str] = []
        for result, model_id in raw:
            if result is not None:
                responses.append(result)
            else:
                failed.append(model_id)

        return responses, failed

    async def synthesize(
        self,
        prompt: str,
        models: list[str],
        *,
        arbiter_model: str | None = None,
        tool_name: str = "design",
        temperature: float = 0.7,
        arbiter_temperature: float = 0.3,
    ) -> ConsensusResult:
        """Full consensus: fan-out to workers then arbiter synthesis.

        Parameters
        ----------
        prompt:
            The user question / task for the worker models.
        models:
            Model ids to fan out to.
        arbiter_model:
            Model id for the arbiter.  When ``None``, uses the
            backend's default model.
        tool_name:
            Prompt template key (``"design"``, ``"review"``,
            ``"implement"``).  See :mod:`loom_ai.prompts`.
        temperature:
            Temperature for worker calls.
        arbiter_temperature:
            Temperature for the arbiter call (lower = more
            deterministic synthesis).
        """
        worker_msgs_raw = build_worker_messages(tool_name, prompt)
        worker_msgs = [
            ChatMessage(role=m["role"], content=m["content"]) for m in worker_msgs_raw
        ]

        responses, failed = await self.gather(
            worker_msgs,
            models,
            temperature=temperature,
        )

        if not responses:
            return ConsensusResult(
                synthesis=ChatResponse(
                    content="All models failed to respond.",
                ),
                worker_responses=[],
                failed_models=failed,
            )

        worker_dicts = [{"model": r.model, "response": r.content} for r in responses]
        arbiter_msgs_raw = build_arbiter_messages(prompt, worker_dicts)
        arbiter_msgs = [
            ChatMessage(role=m["role"], content=m["content"]) for m in arbiter_msgs_raw
        ]

        try:
            synthesis = await self._call_with_retry(
                arbiter_msgs,
                model=arbiter_model,
                temperature=arbiter_temperature,
            )
        except Exception as exc:
            return ConsensusResult(
                synthesis=ChatResponse(
                    content="Arbiter synthesis failed; worker responses are available.",
                ),
                worker_responses=responses,
                failed_models=failed,
                arbiter_attempted=True,
                arbiter_error=f"{type(exc).__name__}: {exc}",
            )

        return ConsensusResult(
            synthesis=synthesis,
            worker_responses=responses,
            failed_models=failed,
            arbiter_attempted=True,
        )

    async def _call_with_retry(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        timeout_seconds: int | None = None,
        retries: int | None = None,
    ) -> ChatResponse:
        """Call backend.chat with deadline timeout and retry."""
        deadline = time.monotonic() + (
            timeout_seconds if timeout_seconds is not None else self._timeout_seconds
        )
        max_retries = retries if retries is not None else self._retries

        last_exc: Exception | None = None
        for attempt in range(1 + max_retries):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return await asyncio.wait_for(
                    self._backend.chat(
                        messages,
                        model=model,
                        temperature=temperature,
                    ),
                    timeout=remaining,
                )
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable(exc):
                    break
                delay = min(
                    (2**attempt) + random.uniform(0, 1),
                    max(0, deadline - time.monotonic()),
                )
                if attempt < max_retries and delay > 0:
                    await asyncio.sleep(delay)

        raise RuntimeError("Arbiter call failed after retries") from last_exc

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Determine whether an exception warrants a retry."""
        if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
            return True
        if isinstance(exc, RuntimeError):
            msg = str(exc).lower()
            if "connection error" in msg:
                return True
            for code in ("429", "500", "502", "503", "504"):
                if code in msg:
                    return True
        return False
