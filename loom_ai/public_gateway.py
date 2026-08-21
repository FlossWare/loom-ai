"""Public free LLM gateway — OpenAI-compatible, keyless, brand-neutral.

When ``LOOM_DEMO_PUBLIC=1`` the server exposes a plain OpenAI-shaped surface
with nothing that ties callers to Loom:

* ``GET  /v1/models``
* ``POST /v1/chat/completions``  (non-stream + ``stream: true``)
* Existing ``/llm/models`` and ``/llm/chat`` remain available

Callers never need a Loom API key.  Upstream provider keys stay server-side
(``LOOM_LLM_API_KEY``).  Responses omit Loom version banners and provider
labels that would identify the gateway.

Environment
-----------
LOOM_DEMO_PUBLIC
    ``1`` / ``true`` enables public mode (keyless LLM surface, restricted
    mounts, generic OpenAPI title).
LOOM_FREE_MODELS
    Comma-separated allowlist of model ids callers may request.  Empty means
    pass-through of whatever the upstream reports (still rate-limited).
LOOM_PUBLIC_RPM
    Per-IP requests-per-minute for the public surface (default ``20``).
LOOM_PUBLIC_MAX_TOKENS
    Hard cap on ``max_tokens`` for public requests (default ``2048``).
"""

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from fastapi import FastAPI

    from loom_ai.config import LoomConfig

logger = logging.getLogger("loom_ai.public_gateway")

_CHUNK_OBJECT = "chat.completion.chunk"
_COMPLETION_OBJECT = "chat.completion"

_RESP_400 = {400: {"description": "Bad request (e.g. model not on free tier)"}}
_RESP_422 = {422: {"description": "Validation error"}}
_RESP_429 = {429: {"description": "Rate limit exceeded"}}
_RESP_502 = {502: {"description": "Upstream LLM error"}}
_RESP_503 = {503: {"description": "No LLM backend configured"}}


def demo_public_enabled() -> bool:
    """Return True when LOOM_DEMO_PUBLIC is set to a truthy value."""
    return os.environ.get("LOOM_DEMO_PUBLIC", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def free_model_allowlist() -> set[str] | None:
    """Parse LOOM_FREE_MODELS.  None means no filter (all upstream models)."""
    raw = os.environ.get("LOOM_FREE_MODELS", "").strip()
    if not raw:
        return None
    return {m.strip() for m in raw.split(",") if m.strip()}


def public_rpm() -> float:
    try:
        return max(1.0, float(os.environ.get("LOOM_PUBLIC_RPM", "20")))
    except ValueError:
        return 20.0


def public_max_tokens_cap() -> int:
    try:
        return max(1, int(os.environ.get("LOOM_PUBLIC_MAX_TOKENS", "2048")))
    except ValueError:
        return 2048


class _IpRateLimiter:
    """In-memory per-IP request counter with a 60s sliding window."""

    def __init__(self, rpm: float) -> None:
        self._rpm = rpm
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, ip: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        window_start = now - 60.0
        hits = [t for t in self._hits[ip] if t > window_start]
        self._hits[ip] = hits
        if len(hits) >= self._rpm:
            oldest = hits[0]
            retry = max(0.0, 60.0 - (now - oldest))
            return False, retry
        hits.append(now)
        return True, 0.0


_limiter: _IpRateLimiter | None = None


def _get_limiter() -> _IpRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _IpRateLimiter(public_rpm())
    return _limiter


def _client_ip(request: Any) -> str:
    """Best-effort client IP (honours X-Forwarded-For from trusted proxy)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_rate(request: Any) -> None:
    from fastapi import HTTPException

    ip = _client_ip(request)
    ok, retry = _get_limiter().check(ip)
    if not ok:
        raise HTTPException(  # NOSONAR — documented in route responses
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(int(retry) + 1)},
        )


def _resolve_model(model: str | None) -> str | None:
    from fastapi import HTTPException

    allow = free_model_allowlist()
    if allow is None:
        return model
    if model is None:
        return next(iter(allow)) if allow else None
    if model not in allow:
        raise HTTPException(  # NOSONAR — documented in route responses
            status_code=400,
            detail=f"Model {model!r} is not available on the free tier",
        )
    return model


def _cap_tokens(max_tokens: int | None) -> int | None:
    cap = public_max_tokens_cap()
    if max_tokens is None:
        return cap
    return min(max_tokens, cap)


async def _list_filtered_models(config: LoomConfig) -> list[str]:
    if config.llm is None:
        return []
    try:
        models = await config.llm.list_models()
    except Exception:
        logger.exception("list_models failed")
        models = []
    allow = free_model_allowlist()
    if allow is None:
        return models
    filtered = [m for m in models if m in allow]
    for mid in allow:
        if mid not in filtered:
            filtered.append(mid)
    return filtered


def _openai_completion_payload(
    *,
    content: str,
    model: str,
    usage: dict,
) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": _COMPLETION_OBJECT,
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        },
    }


def _sse_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict,
    finish: str | None,
) -> str:
    payload = {
        "id": completion_id,
        "object": _CHUNK_OBJECT,
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_response(
    cfg: LoomConfig,
    messages: list,
    model: str | None,
    temperature: float,
    max_tokens: int | None,
):
    from fastapi.responses import StreamingResponse

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model_label = model or ""

    async def gen() -> AsyncIterator[str]:
        yield _sse_chunk(
            completion_id,
            created,
            model_label,
            {"role": "assistant", "content": ""},
            None,
        )
        try:
            async for token in cfg.llm.chat_stream(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield _sse_chunk(
                    completion_id, created, model_label, {"content": token}, None
                )
            yield _sse_chunk(completion_id, created, model_label, {}, "stop")
            yield "data: [DONE]\n\n"
        except Exception as exc:
            err = {"error": {"message": type(exc).__name__, "type": "server_error"}}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def mount_public_v1_routes(app: FastAPI, config: LoomConfig) -> None:
    """Mount OpenAI-compatible ``/v1`` routes (always unauthenticated)."""
    from fastapi import APIRouter, HTTPException, Request

    try:
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError("Public gateway requires pydantic (server extra).") from exc

    class V1Message(BaseModel):
        role: str
        content: str

    class V1ChatRequest(BaseModel):
        model: str | None = None
        messages: list[V1Message]
        temperature: float = 0.7
        max_tokens: int | None = None
        stream: bool = False

    router = APIRouter(prefix="/v1", tags=["openai-compatible"])

    @router.get("/models", responses={**_RESP_429})
    async def v1_models(request: Request):
        _enforce_rate(request)
        models = await _list_filtered_models(config)
        data = [
            {"id": mid, "object": "model", "created": 0, "owned_by": "free"}
            for mid in models
        ]
        return {"object": "list", "data": data}

    @router.post(
        "/chat/completions",
        responses={**_RESP_400, **_RESP_422, **_RESP_429, **_RESP_502, **_RESP_503},
    )
    async def v1_chat_completions(body: V1ChatRequest, request: Request):
        _enforce_rate(request)
        if config.llm is None:
            raise HTTPException(status_code=503, detail="No LLM backend configured")

        from loom_ai.models import ChatMessage

        model = _resolve_model(body.model)
        max_tokens = _cap_tokens(body.max_tokens)
        messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
        if not messages:
            raise HTTPException(status_code=422, detail="messages must not be empty")

        if body.stream:
            return await _stream_response(
                config, messages, model, body.temperature, max_tokens
            )

        try:
            resp = await config.llm.chat(
                messages,
                model=model,
                temperature=body.temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.exception("chat failed")
            raise HTTPException(
                status_code=502, detail=f"Upstream error: {type(exc).__name__}"
            ) from exc

        return _openai_completion_payload(
            content=resp.content,
            model=resp.model or (model or ""),
            usage=resp.usage,
        )

    app.include_router(router)
    logger.info("Mounted public OpenAI-compatible /v1 routes (keyless)")
