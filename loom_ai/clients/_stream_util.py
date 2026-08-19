"""Helpers for LoomClient.chat_stream error propagation."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def run_stream_producer(
    req: urllib.request.Request,
    timeout: int,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Background producer: push tokens, then exception or None sentinel."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode(errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk and not chunk.get("choices"):
                    raise RuntimeError(str(chunk.get("error") or "stream error"))
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {}).get("content", "")
                if not delta and "delta" in chunk:
                    delta = chunk.get("delta") or ""
                if delta:
                    loop.call_soon_threadsafe(queue.put_nowait, delta)
    except Exception as exc:
        logger.exception("Stream error: %s", exc)
        loop.call_soon_threadsafe(queue.put_nowait, exc)
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


async def iterate_stream_queue(
    queue: asyncio.Queue,
):
    """Yield tokens; re-raise any BaseException placed on the queue."""
    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, BaseException):
            raise item
        yield item
