#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -d .venv ]] || { echo "Run ./scripts/install.sh first." >&2; exit 1; }
if [[ ! -f .env ]]; then cp .env.example .env; echo "Created .env. Review it before dogfooding."; else echo "Existing .env preserved."; fi
echo "Setup complete. Run ./scripts/doctor.sh."
