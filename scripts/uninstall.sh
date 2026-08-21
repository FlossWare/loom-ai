#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT/.venv" ]]; then rm -rf "$ROOT/.venv"; echo "Removed $ROOT/.venv"; else echo "No repository-local .venv found."; fi
echo "Source, configuration, Podman, and system packages were left untouched."
