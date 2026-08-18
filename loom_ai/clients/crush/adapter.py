"""Crush MCP consensus server adapter.

Configures Crush (github.com/FlossWare/crush) to use loom-ai as its
backend.  Crush connects via a LiteLLM proxy with a single master key.

Usage::

    # Generate crush config pointing at loom-ai
    python -m loom_ai.clients.crush

    # Or use programmatically
    from loom_ai.clients.crush.adapter import generate_config
    config = generate_config("http://localhost:5000")
"""

from __future__ import annotations

import json
import os
import shlex
import sys


def generate_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
) -> dict:
    """Generate a Crush-compatible configuration for loom-ai.

    Crush uses loom-ai's ``/llm/chat`` endpoint as an OpenAI-compatible
    backend and ``/consensus/synthesize`` for multi-model consensus.
    """
    return {
        "provider": {
            "type": "openai-compatible",
            "base_url": f"{loom_url}/llm",
            "api_key": api_key or "loom-ai",
        },
        "consensus": {
            "endpoint": f"{loom_url}/consensus/synthesize",
            "gather_endpoint": f"{loom_url}/consensus/gather",
            "api_key": api_key,
        },
        "knowledge": {
            "search_endpoint": f"{loom_url}/search/text",
            "store_endpoint": f"{loom_url}/knowledge/documents",
            "api_key": api_key,
        },
    }


def generate_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
) -> str:
    """Generate shell export statements for Crush environment."""
    lines = [
        f"export CRUSH_LLM_BASE_URL={shlex.quote(f'{loom_url}/llm')}",
        f"export CRUSH_LLM_API_KEY={shlex.quote(api_key)}",
        f"export CRUSH_CONSENSUS_URL={shlex.quote(f'{loom_url}/consensus')}",
    ]
    return "\n".join(lines)


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")

    if "--env" in sys.argv:
        print(generate_env(loom_url, api_key))
    else:
        config = generate_config(loom_url, api_key)
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
