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


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install server extra: pip install flossware-loom-ai[server]"
        ) from exc

    from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

    from loom_ai.config import LoomConfig
    from loom_ai.server import create_app

    config = asyncio.run(LoomConfig.from_env())
    app = create_app(config)

    chat_html = Path(__file__).resolve().parent.parent / "static" / "chat.html"
    route_paths = {getattr(r, "path", None) for r in app.routes}

    if "/ui" not in route_paths:

        @app.get("/ui")
        async def chat_ui():
            return HTMLResponse(chat_html.read_text(encoding="utf-8"))

        @app.get("/")
        async def root():
            return RedirectResponse(url="/ui")

    if config.llm is not None and "/llm/chat/stream" not in route_paths:
        from loom_ai.models import ChatMessage

        @app.post("/llm/chat/stream")
        async def llm_chat_stream(request):  # type: ignore[no-untyped-def]
            body = await request.json()
            messages = [
                ChatMessage(role=m["role"], content=m["content"])
                for m in body.get("messages", [])
            ]

            async def gen():
                try:
                    async for token in config.llm.chat_stream(
                        messages,
                        model=body.get("model"),
                        temperature=float(body.get("temperature", 0.7)),
                        max_tokens=body.get("max_tokens"),
                    ):
                        payload = json.dumps({"delta": token})
                        yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    payload = json.dumps({"error": type(exc).__name__})
                    yield f"data: {payload}\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")

    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    port = int(os.environ.get("LOOM_PORT", "5000"))
    print(f"Loom Chat UI → http://{host}:{port}/ui")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
