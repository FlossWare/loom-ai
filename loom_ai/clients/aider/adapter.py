"""Aider CLI adapter for loom-ai.

Configures Aider to use loom-ai as its LLM backend via OpenAI-compatible API.

Usage::

    # Print aider flags
    python -m loom_ai.clients.aider

    # Or set env for aider:
    export OPENAI_API_BASE=http://127.0.0.1:5000/llm
    export OPENAI_API_KEY=loom-ai
    aider --model gpt-4o-mini
"""

from __future__ import annotations

import os
import sys


def get_aider_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> dict[str, str]:
    """Return environment variables for Aider to use loom-ai."""
    return {
        "OPENAI_API_BASE": f"{loom_url}/llm",
        "OPENAI_API_KEY": api_key or "loom-ai",
        "AIDER_MODEL": model,
    }


def get_aider_args(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> list[str]:
    """Return CLI arguments to point Aider at loom-ai."""
    return [
        "--openai-api-base",
        f"{loom_url}/llm",
        "--openai-api-key",
        api_key or "loom-ai",
        "--model",
        model,
    ]


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")
    model = os.environ.get("LOOM_MODEL", "gpt-4o-mini")

    if "--env" in sys.argv:
        for k, v in get_aider_env(loom_url, api_key, model).items():
            print(f"export {k}={v}")
    else:
        print(" ".join(get_aider_args(loom_url, api_key, model)))


if __name__ == "__main__":
    main()
