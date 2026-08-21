#!/usr/bin/env bash

# Shared helpers for Loom operator scripts. Source this file from scripts;
# keep it free of side effects so scripts remain composable.

loom_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

loom_python() {
  local root
  root="$(loom_root)"
  if [[ -x "$root/.venv/bin/python" ]]; then
    printf '%s\n' "$root/.venv/bin/python"
  else
    command -v python3
  fi
}
