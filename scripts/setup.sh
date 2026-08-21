#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Missing .venv. Run ./scripts/install.sh first." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example. Review it before dogfooding."
  else
    echo "No .env.example exists yet. Configuration must be supplied via environment variables."
  fi
else
  echo "Existing .env preserved."
fi

# Never print secrets. Show only whether the expected runtime configuration exists.
if [[ -z "${LOOM_STORAGE:-}" && -z "${LOOM_LLM_BASE_URL:-}" && -z "${LOOM_LLM_PROVIDER:-}" ]]; then
  echo "Note: runtime configuration is not exported in this shell. Configure .env or the environment before dogfood."
fi

echo "Setup complete. Run ./scripts/doctor.sh before starting Loom."
