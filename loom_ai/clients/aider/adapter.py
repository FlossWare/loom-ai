"""Aider adapter for loom-ai.

Configures Aider (github.com/Aider-AI/aider) to use loom-ai as its LLM
backend.  Aider supports OpenAI-compatible endpoints via environment
variables and command-line flags.

Usage::

    # Generate aider environment variables
    python -m loom_ai.clients.aider --env

    # Generate aider command line
    python -m loom_ai.clients.aider --cmd

    # Run aider through loom-ai directly
    eval $(python -m loom_ai.clients.aider --env) && aider

Integration::

    # Via environment
    export OPENAI_API_BASE="http://127.0.0.1:5000/llm"
    export OPENAI_API_KEY="loom-ai"
    aider --model openai/gpt-4o-mini

    # Via command line
    aider --openai-api-base http://127.0.0.1:5000/llm \\
          --openai-api-key loom-ai \\
          --model openai/gpt-4o-mini

    # Via .aider.conf.yml
    openai-api-base: http://127.0.0.1:5000/llm
    openai-api-key: loom-ai
    model: openai/gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import shlex
import sys


def generate_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> str:
    """Generate shell exports for Aider."""
    return "\n".join([
        f"export OPENAI_API_BASE={shlex.quote(f'{loom_url}/llm')}",
        f"export OPENAI_API_KEY={shlex.quote(api_key or 'loom-ai')}",
    ])


def generate_cmd(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> str:
    """Generate aider command line."""
    return (
        f"aider --openai-api-base {shlex.quote(f'{loom_url}/llm')} "
        f"--openai-api-key {shlex.quote(api_key or 'loom-ai')} "
        f"--model {shlex.quote(f'openai/{model}')}"
    )


def generate_yaml(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> str:
    """Generate .aider.conf.yml content."""
    return "\n".join([
        f"openai-api-base: {loom_url}/llm",
        f"openai-api-key: {api_key or 'loom-ai'}",
        f"model: openai/{model}",
    ])


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")
    model = os.environ.get("LOOM_MODEL", "gpt-4o-mini")

    if "--env" in sys.argv:
        print(generate_env(loom_url, api_key, model))
    elif "--cmd" in sys.argv:
        print(generate_cmd(loom_url, api_key, model))
    elif "--yaml" in sys.argv:
        print(generate_yaml(loom_url, api_key, model))
    else:
        print(json.dumps({
            "env": generate_env(loom_url, api_key, model),
            "cmd": generate_cmd(loom_url, api_key, model),
            "yaml": generate_yaml(loom_url, api_key, model),
        }, indent=2))


if __name__ == "__main__":
    main()
