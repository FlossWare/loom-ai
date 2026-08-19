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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loom_ai.config import LoomConfig

# Static UI is package data — never taken from the request path.
_CHAT_HTML = Path(__file__).resolve().parent.parent / "static" / "chat.html"


def _parse_messages(raw_msgs: object) -> list:
    """Validate and convert raw message dicts to ChatMessage objects.

    Raises HTTPException(422) on invalid input.
    """
    from fastapi import HTTPException

    from loom_ai.models import ChatMessage

    if not isinstance(raw_msgs, list) or not raw_msgs:
        raise HTTPException(status_code=422, detail="messages required")
    messages: list[ChatMessage] = []
    for m in raw_msgs:
        if not isinstance(m, dict) or "role" not in m or "content" not in m:
            raise HTTPException(status_code=422, detail="invalid message")
        messages.append(
            ChatMessage(role=str(m["role"]), content=str(m["content"]))
        )
    return messages


def _mount_ui_routes(app: object) -> None:
    """Register /ui and / routes on *app*."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, RedirectResponse

    @app.get("/ui")  # type: ignore[attr-defined]
    async def chat_ui():
        if not _CHAT_HTML.is_file():
            raise HTTPException(status_code=404, detail="Chat UI not installed")
        return FileResponse(
            path=_CHAT_HTML,
            media_type="text/html; charset=utf-8",
        )

    @app.get("/")  # type: ignore[attr-defined]
    async def root():
        return RedirectResponse(url="/ui")


def _mount_stream_route(app: object, config: LoomConfig) -> None:
    """Register /llm/chat/stream SSE endpoint on *app*."""
    from fastapi.responses import StreamingResponse

    @app.post("/llm/chat/stream")  # type: ignore[attr-defined]
    async def llm_chat_stream(request):  # noqa: ANN001
        body = await request.json()
        messages = _parse_messages(body.get("messages"))
        temperature = float(body.get("temperature", 0.7))
        raw_model = body.get("model")
        raw_max = body.get("max_tokens")
        model = raw_model if isinstance(raw_model, str) else None
        max_tokens = raw_max if isinstance(raw_max, int) else None

        async def gen():
            try:
                async for token in config.llm.chat_stream(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield f"data: {json.dumps({'delta': token})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:  # noqa: BLE001
                err_type = type(exc).__name__
                yield f"data: {json.dumps({'error': err_type})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")


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
    print(f"Loom Chat UI → http://{host}:{port}/ui")  # noqa: T201
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
