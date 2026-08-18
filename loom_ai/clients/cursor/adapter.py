"""Cursor adapter for loom-ai.

Configures Cursor IDE to use loom-ai as its LLM backend.  Cursor
supports OpenAI-compatible endpoints via its settings.

Usage::

    # Generate Cursor settings
    python -m loom_ai.clients.cursor

    # Generate environment variables
    python -m loom_ai.clients.cursor --env

Integration:
    In Cursor Settings > Models > OpenAI API Key:
    - Set API Key to your LOOM_API_KEY
    - Set Base URL to http://127.0.0.1:5000/llm
    - Enable "Override OpenAI Base URL"

    Or use environment variables to configure Cursor globally.
"""

from __future__ import annotations

import json
import os
import shlex
import sys


def generate_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> dict:
    """Generate Cursor-compatible settings for loom-ai."""
    return {
        "openai.apiKey": api_key or "loom-ai",
        "openai.baseUrl": f"{loom_url}/llm",
        "openai.model": model,
        "instructions": (
            "Settings > Models > OpenAI API Key:\n"
            f"  API Key: {api_key or 'loom-ai'}\n"
            f"  Base URL: {loom_url}/llm\n"
            "  Enable 'Override OpenAI Base URL'"
        ),
    }


def generate_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> str:
    """Generate shell exports for Cursor."""
    lines = [
        f"export OPENAI_API_KEY={shlex.quote(api_key or 'loom-ai')}",
        f"export OPENAI_BASE_URL={shlex.quote(f'{loom_url}/llm')}",
        f"export CURSOR_MODEL={shlex.quote(model)}",
    ]
    return "\n".join(lines)


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")
    model = os.environ.get("LOOM_MODEL", "gpt-4o-mini")

    if "--env" in sys.argv:
        print(generate_env(loom_url, api_key, model))
    else:
        config = generate_config(loom_url, api_key, model)
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
