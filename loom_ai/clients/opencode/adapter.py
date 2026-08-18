"""OpenCode adapter for loom-ai.

Configures OpenCode (github.com/nicepkg/opencode) to use loom-ai as its
LLM backend.  OpenCode supports OpenAI-compatible endpoints natively.

Usage::

    # Generate opencode config
    python -m loom_ai.clients.opencode

    # Apply directly to opencode config
    python -m loom_ai.clients.opencode --write

Environment::

    LOOM_URL       loom-ai server URL (default: http://127.0.0.1:5000)
    LOOM_API_KEY   Bearer token for authentication
    LOOM_MODEL     Default model (default: gpt-4o-mini)
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path


def generate_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> dict:
    """Generate an OpenCode-compatible configuration for loom-ai."""
    return {
        "provider": "openai-compatible",
        "providers": {
            "openai-compatible": {
                "apiKey": api_key or "loom-ai",
                "baseURL": f"{loom_url}/llm",
            },
        },
        "model": model,
    }


def generate_env(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> str:
    """Generate shell export statements for OpenCode."""
    lines = [
        f"export OPENAI_BASE_URL={shlex.quote(f'{loom_url}/llm')}",
        f"export OPENAI_API_KEY={shlex.quote(api_key or 'loom-ai')}",
        f"export OPENCODE_MODEL={shlex.quote(model)}",
    ]
    return "\n".join(lines)


def _config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "opencode" / "config.json"


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")
    model = os.environ.get("LOOM_MODEL", "gpt-4o-mini")

    config = generate_config(loom_url, api_key, model)

    if "--env" in sys.argv:
        print(generate_env(loom_url, api_key, model))
    elif "--write" in sys.argv:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(f"Wrote OpenCode config to {path}")
    else:
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
