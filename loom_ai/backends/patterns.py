"""Pluggable multi-model execution patterns for loom-ai.

Provides three ``ExecutionPattern`` implementations that satisfy the
protocol defined in ``contracts_phase1.py``:

- **ConsensusPattern** -- fan-out to all models, collect responses,
  surface the most common answer.
- **CascadePattern** -- try models in priority order, return the first
  success.
- **MapReducePattern** -- distribute the task across models in parallel,
  then combine results.

Each pattern works with either a ``ModelRouter`` (per-model backend
resolution) or a single ``LLMBackend`` used for every model.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import TYPE_CHECKING

from loom_ai.models import ChatMessage, ChatResponse
from loom_ai.models_phase1 import PatternResult

if TYPE_CHECKING:
    from loom_ai.contracts_phase1 import ModelRouter
    from loom_ai.protocols import LLMBackend

_MISSING_BACKEND_MSG = "Either router or backend must be provided"


async def _call_model(
    task: str,
    model: str,
    *,
    router: ModelRouter | None = None,
    backend: LLMBackend | None = None,
    _config: dict | None = None,
) -> ChatResponse:
    """Send *task* to a single model via *router* or *backend*.

    Raises ``ValueError`` if neither *router* nor *backend* is provided.
    """
    if router is not None:
        resolved_backend = await router.route(model)
        return await resolved_backend.chat(
            [ChatMessage(role="user", content=task)],
        )

    if backend is not None:
        return await backend.chat(
            [ChatMessage(role="user", content=task)],
            model=model,
        )

    raise ValueError(_MISSING_BACKEND_MSG)


class ConsensusPattern:
    """Fan-out a task to all models in parallel and collect responses.

    The most frequently occurring response content is surfaced in
    ``metadata["consensus"]``.  All individual responses are returned
    in ``results``.
    """

    async def execute(
        self,
        task: str,
        *,
        models: list[str],
        router: ModelRouter | None = None,
        backend: LLMBackend | None = None,
        config: dict | None = None,
    ) -> PatternResult:
        if router is None and backend is None:
            raise ValueError(_MISSING_BACKEND_MSG)

        start = time.perf_counter()

        async def _worker(model: str) -> dict:
            try:
                resp = await _call_model(
                    task, model, router=router, backend=backend, _config=config
                )
                return {"model": model, "content": resp.content, "success": True}
            except Exception as exc:
                return {
                    "model": model,
                    "error": f"{type(exc).__name__}: {exc}",
                    "success": False,
                }

        raw = await asyncio.gather(*[_worker(m) for m in models])
        results = list(raw)

        # Determine most common answer among successes.
        successful = [r["content"] for r in results if r.get("success")]
        consensus = ""
        if successful:
            counter = Counter(successful)
            consensus = counter.most_common(1)[0][0]

        duration_ms = (time.perf_counter() - start) * 1000

        return PatternResult(
            pattern="consensus",
            results=results,
            metadata={
                "consensus": consensus,
                "total": len(models),
                "succeeded": len(successful),
                "failed": len(models) - len(successful),
            },
            duration_ms=duration_ms,
        )


class CascadePattern:
    """Try models in order and return the first successful response.

    Models are attempted sequentially; if a model raises an exception
    the next model in the list is tried.  ``metadata["model_used"]``
    records which model ultimately succeeded.
    """

    async def execute(
        self,
        task: str,
        *,
        models: list[str],
        router: ModelRouter | None = None,
        backend: LLMBackend | None = None,
        config: dict | None = None,
    ) -> PatternResult:
        if router is None and backend is None:
            raise ValueError(_MISSING_BACKEND_MSG)

        start = time.perf_counter()
        errors: list[dict] = []

        for model in models:
            try:
                resp = await _call_model(
                    task, model, router=router, backend=backend, _config=config
                )
                duration_ms = (time.perf_counter() - start) * 1000
                return PatternResult(
                    pattern="cascade",
                    results=[
                        {"model": model, "content": resp.content, "success": True}
                    ],
                    metadata={
                        "model_used": model,
                        "attempts": len(errors) + 1,
                        "errors": errors,
                    },
                    duration_ms=duration_ms,
                )
            except Exception as exc:
                errors.append({"model": model, "error": f"{type(exc).__name__}: {exc}"})

        duration_ms = (time.perf_counter() - start) * 1000
        return PatternResult(
            pattern="cascade",
            results=[],
            metadata={
                "model_used": None,
                "attempts": len(errors),
                "errors": errors,
            },
            duration_ms=duration_ms,
        )


class MapReducePattern:
    """Distribute a task across models in parallel, then combine results.

    Each model receives the task (or ``config["map_prompt"]`` if
    provided).  All successful responses are collected, and a combined
    summary is placed in ``metadata["combined"]``.
    """

    async def execute(
        self,
        task: str,
        *,
        models: list[str],
        router: ModelRouter | None = None,
        backend: LLMBackend | None = None,
        config: dict | None = None,
    ) -> PatternResult:
        if router is None and backend is None:
            raise ValueError(_MISSING_BACKEND_MSG)

        start = time.perf_counter()
        cfg = config or {}
        map_prompt = cfg.get("map_prompt", task)

        async def _worker(model: str) -> dict:
            try:
                resp = await _call_model(
                    map_prompt, model, router=router, backend=backend, _config=config
                )
                return {"model": model, "content": resp.content, "success": True}
            except Exception as exc:
                return {
                    "model": model,
                    "error": f"{type(exc).__name__}: {exc}",
                    "success": False,
                }

        raw = await asyncio.gather(*[_worker(m) for m in models])
        results = list(raw)

        successful_contents = [r["content"] for r in results if r.get("success")]
        combined = "\n---\n".join(successful_contents)

        duration_ms = (time.perf_counter() - start) * 1000

        return PatternResult(
            pattern="map_reduce",
            results=results,
            metadata={
                "combined": combined,
                "total": len(models),
                "succeeded": len(successful_contents),
                "failed": len(models) - len(successful_contents),
            },
            duration_ms=duration_ms,
        )
