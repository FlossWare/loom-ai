#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -r /etc/os-release ]] || { echo "Cannot identify OS." >&2; exit 1; }
. /etc/os-release
[[ "${ID:-}" == fedora ]] || { echo "Fedora is the first supported Linux target; found ${PRETTY_NAME:-unknown}." >&2; exit 2; }
command -v dnf >/dev/null || { echo "dnf is required." >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || { echo "Python 3.11+ is required." >&2; exit 1; }
packages=()
for cmd in git curl gh podman; do command -v "$cmd" >/dev/null 2>&1 || packages+=("$cmd"); done
command -v pg_isready >/dev/null 2>&1 || packages+=(postgresql)
if ((${#packages[@]})); then sudo dnf install -y "${packages[@]}"; fi
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
rootless="$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
[[ "$rootless" == true ]] || { echo "Podman rootless mode is unavailable for this user." >&2; exit 1; }
echo "Loom installed: $ROOT/.venv"
echo "Podman: $(podman --version)"
echo "Next: ./scripts/setup.sh && ./scripts/doctor.sh"
