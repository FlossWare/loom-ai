#!/usr/bin/env bash
set -euo pipefail

# Fedora-first Loom installer. Installs into a repository-local .venv by default.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify operating system." >&2
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "fedora" ]]; then
  echo "Loom's first-class installer currently supports Fedora only." >&2
  echo "Detected: ${PRETTY_NAME:-unknown}" >&2
  exit 2
fi

command -v dnf >/dev/null 2>&1 || { echo "dnf is required." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required." >&2; exit 1; }

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || {
  echo "Python 3.11+ is required." >&2
  exit 1
}

# Install only host tools that the operator workflow actually needs.
missing=()
for cmd in git curl; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
command -v gh >/dev/null 2>&1 || missing+=("gh")

if ((${#missing[@]})); then
  echo "Installing Fedora packages: ${missing[*]}"
  sudo dnf install -y "${missing[@]}"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

echo
echo "Loom installed in: $ROOT/.venv"
echo "Activate with: source .venv/bin/activate"
echo "Next: ./scripts/setup.sh && ./scripts/doctor.sh"
