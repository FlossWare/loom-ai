"""Claude-like chat UI entrypoint.

Run::

    python -m loom_ai.clients.chat_ui

Serves the FastAPI app with the /ui chat SPA (and adds stream/UI routes
if the installed server module does not yet include them).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

# Static UI is package data — never taken from the request path.
_CHAT_HTML = Path(__file__).resolve().parent.parent / "static" / "chat.html"


def _parse_messages(raw_msgs: Any) -> list[Any]:
    """Validate and convert request messages; raises HTTPException."""
    from fastapi import HTTPException

    from loom_ai.models import ChatMessage

    if not isinstance(raw_msgs, list) or not raw_msgs:
        raise HTTPException(status_code=422, detail="messages required")
    messages: list[ChatMessage] = []
    for m in raw_msgs:
        if not isinstance(m, dict) or "role" not in m or "content" not in m:
            raise HTTPException(status_code=422, detail="invalid message")
        messages.append(ChatMessage(role=str(m["role"]), content=str(m["content"])))
    return messages


def _stream_params(body: dict[str, Any]) -> tuple[str | None, float, int | None]:
    model = body.get("model")
    model_s = model if isinstance(model, str) else None
    temperature = float(body.get("temperature", 0.7))
    max_tokens = body.get("max_tokens")
    max_t = max_tokens if isinstance(max_tokens, int) else None
    return model_s, temperature, max_t


def _sse_generator(
    llm: Any,
    messages: list[Any],
    model: str | None,
    temperature: float,
    max_tokens: int | None,
):
    async def gen():
        try:
            async for token in llm.chat_stream(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield f"data: {json.dumps({'delta': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': type(exc).__name__})}\n\n"

    return gen()


def _mount_ui_routes(app: Any) -> None:
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, RedirectResponse

    @app.get("/ui")
    async def chat_ui():
        if not _CHAT_HTML.is_file():
            raise HTTPException(status_code=404, detail="Chat UI not installed")
        return FileResponse(
            path=_CHAT_HTML,
            media_type="text/html; charset=utf-8",
        )

    @app.get("/")
    async def root():
        return RedirectResponse(url="/ui")


def _mount_stream_route(app: Any, config: Any) -> None:
    from fastapi import Request
    from fastapi.responses import StreamingResponse

    @app.post("/llm/chat/stream")
    async def llm_chat_stream(request: Request):
        body = await request.json()
        messages = _parse_messages(body.get("messages"))
        model, temperature, max_tokens = _stream_params(body)
        return StreamingResponse(
            _sse_generator(config.llm, messages, model, temperature, max_tokens),
            media_type="text/event-stream",
        )


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install server extra: pip install flossware-loom-ai[server]"
        ) from exc

    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    config = asyncio.run(LoomConfig.from_env())
    app = create_app(config)
    route_paths = {getattr(r, "path", None) for r in app.routes}

    if "/ui" not in route_paths:
        _mount_ui_routes(app)

    if config.llm is not None and "/llm/chat/stream" not in route_paths:
        _mount_stream_route(app, config)

    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    port = int(os.environ.get("LOOM_PORT", "5000"))
    print(f"Loom Chat UI → http://{host}:{port}/ui")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
