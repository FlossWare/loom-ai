#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

./scripts/doctor.sh

if [[ "${LOOM_CANARY:-1}" != "1" ]]; then
  echo "Refusing dogfood: LOOM_CANARY must be 1." >&2
  exit 1
fi

if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi

# Keep the entry point deliberately thin. The Python acceptance harness owns
# the actual evidence-producing qualification contract.
exec "$PY" -m loom_ai.acceptance "$@"
