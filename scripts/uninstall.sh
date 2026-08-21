#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  rm -rf .venv
  echo "Removed Loom virtual environment: $ROOT/.venv"
else
  echo "No repository-local .venv found."
fi

echo "Source checkout and configuration were preserved."
echo "System packages were not removed."
