"""Regression: LoomClient.chat_stream must propagate remote errors."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from loom_ai.clients.client import ClientConfig, LoomClient


@pytest.mark.asyncio
async def test_chat_stream_propagates_http_error():
    client = LoomClient(ClientConfig(base_url="http://example.test", timeout=5))

    def boom(*_a, **_k):
        raise OSError("connection reset")

    with patch("urllib.request.urlopen", side_effect=boom):
        with pytest.raises(OSError, match="connection reset"):
            async for _ in client.chat_stream([{"role": "user", "content": "hi"}]):
                pass


@pytest.mark.asyncio
async def test_chat_stream_yields_then_raises():
    client = LoomClient(ClientConfig(base_url="http://example.test", timeout=5))

    lines = [
        b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n',
        b"data: [DONE]\n",
    ]

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            yield from lines

    with patch("urllib.request.urlopen", return_value=_Resp()):
        tokens = []
        async for t in client.chat_stream([{"role": "user", "content": "hi"}]):
            tokens.append(t)
        assert tokens == ["Hello"]
