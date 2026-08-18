"""Continue.dev adapter for loom-ai.

Configures Continue (continue.dev) to use loom-ai as its LLM backend.
Continue supports OpenAI-compatible endpoints via its config.json.

Usage::

    # Generate continue config
    python -m loom_ai.clients.continue_dev

    # Write to Continue config directory
    python -m loom_ai.clients.continue_dev --write

Integration:
    Add to ~/.continue/config.json under "models":

    {
      "title": "loom-ai",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "apiBase": "http://127.0.0.1:5000/llm",
      "apiKey": "loom-ai"
    }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def generate_model_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
    title: str = "loom-ai",
) -> dict:
    """Generate a Continue model entry for loom-ai."""
    return {
        "title": title,
        "provider": "openai",
        "model": model,
        "apiBase": f"{loom_url}/llm",
        "apiKey": api_key or "loom-ai",
    }


def generate_full_config(
    loom_url: str = "http://127.0.0.1:5000",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> dict:
    """Generate a minimal Continue config.json with loom-ai as the model."""
    return {
        "models": [generate_model_config(loom_url, api_key, model)],
        "tabAutocompleteModel": generate_model_config(
            loom_url, api_key, model,
            title="loom-ai-autocomplete",
        ),
    }


def _config_path() -> Path:
    return Path.home() / ".continue" / "config.json"


def main() -> None:
    loom_url = os.environ.get("LOOM_URL", "http://127.0.0.1:5000")
    api_key = os.environ.get("LOOM_API_KEY", "")
    model = os.environ.get("LOOM_MODEL", "gpt-4o-mini")

    if "--model-only" in sys.argv:
        print(json.dumps(generate_model_config(loom_url, api_key, model), indent=2))
    elif "--write" in sys.argv:
        path = _config_path()
        config = {}
        if path.exists():
            config = json.loads(path.read_text())
        models = config.get("models", [])
        models = [m for m in models if m.get("title") != "loom-ai"]
        models.append(generate_model_config(loom_url, api_key, model))
        config["models"] = models
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(f"Added loom-ai model to {path}")
    else:
        print(json.dumps(generate_full_config(loom_url, api_key, model), indent=2))


if __name__ == "__main__":
    main()
