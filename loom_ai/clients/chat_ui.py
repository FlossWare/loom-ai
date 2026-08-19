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

# Static UI is package data — never taken from the request path.
_CHAT_HTML = Path(__file__).resolve().parent.parent / "static" / "chat.html"


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install server extra: pip install flossware-loom-ai[server]"
        ) from exc

    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    config = asyncio.run(LoomConfig.from_env())
    app = create_app(config)

    route_paths = {getattr(r, "path", None) for r in app.routes}

    if "/ui" not in route_paths:

        @app.get("/ui")
        async def chat_ui():
            if not _CHAT_HTML.is_file():
                raise HTTPException(status_code=404, detail="Chat UI not installed")
            # FileResponse serves a fixed package path (not user-controlled).
            return FileResponse(
                path=_CHAT_HTML,
                media_type="text/html; charset=utf-8",
            )

        @app.get("/")
        async def root():
            return RedirectResponse(url="/ui")

    if config.llm is not None and "/llm/chat/stream" not in route_paths:
        from loom_ai.models import ChatMessage

        @app.post("/llm/chat/stream")
        async def llm_chat_stream(request: Request):
            body = await request.json()
            raw_msgs = body.get("messages")
            if not isinstance(raw_msgs, list) or not raw_msgs:
                raise HTTPException(status_code=422, detail="messages required")
            messages: list[ChatMessage] = []
            for m in raw_msgs:
                if not isinstance(m, dict) or "role" not in m or "content" not in m:
                    raise HTTPException(status_code=422, detail="invalid message")
                messages.append(
                    ChatMessage(role=str(m["role"]), content=str(m["content"]))
                )
            temperature = float(body.get("temperature", 0.7))
            model = body.get("model")
            max_tokens = body.get("max_tokens")

            async def gen():
                try:
                    async for token in config.llm.chat_stream(
                        messages,
                        model=model if isinstance(model, str) else None,
                        temperature=temperature,
                        max_tokens=max_tokens if isinstance(max_tokens, int) else None,
                    ):
                        yield f"data: {json.dumps({'delta': token})}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    yield f"data: {json.dumps({'error': type(exc).__name__})}\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")

    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    port = int(os.environ.get("LOOM_PORT", "5000"))
    print(f"Loom Chat UI → http://{host}:{port}/ui")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
