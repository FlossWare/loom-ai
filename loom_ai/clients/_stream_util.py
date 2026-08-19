"""Helpers for LoomClient.chat_stream error propagation."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


class StreamProtocolError(RuntimeError):
    """Malformed SSE payload in a remote chat stream."""


def _delta_from_chunk(chunk: dict) -> str:
    """Extract a text delta from an SSE JSON payload."""
    if "error" in chunk and not chunk.get("choices"):
        raise RuntimeError(str(chunk.get("error") or "stream error"))
    choice = chunk.get("choices", [{}])[0]
    delta = choice.get("delta", {}).get("content") or chunk.get("delta")
    return str(delta) if delta else ""


def _handle_data_line(
    payload: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> bool:
    """Process one SSE data payload. Return False to stop the stream.

    Raises ``StreamProtocolError`` on malformed JSON (propagated by caller).
    """
    if payload == "[DONE]":
        return False
    try:
        chunk = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StreamProtocolError(f"malformed SSE JSON: {exc}") from exc
    delta = _delta_from_chunk(chunk)
    if delta:
        loop.call_soon_threadsafe(queue.put_nowait, delta)
    return True


def _read_sse_lines(resp, queue, loop):
    """Process SSE lines from an HTTP response."""
    for raw_line in resp:
        line = raw_line.decode(errors="replace").strip()
        if line.startswith("data: ") and not _handle_data_line(line[6:], queue, loop):
            break


def run_stream_producer(
    req: urllib.request.Request,
    timeout: int,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Background producer: push tokens, then exception or None sentinel."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _read_sse_lines(resp, queue, loop)
    except Exception as exc:
        logger.exception("Stream error: %s", exc)
        loop.call_soon_threadsafe(queue.put_nowait, exc)
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


async def iterate_stream_queue(queue: asyncio.Queue):
    """Yield tokens; re-raise any BaseException placed on the queue."""
    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, BaseException):
            raise item
        yield item
