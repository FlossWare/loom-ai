#!/usr/bin/env bash
set -u

PASS=0
FAIL=0
WARN=0

ok() { printf 'PASS  %-20s %s\n' "$1" "$2"; PASS=$((PASS + 1)); }
bad() { printf 'FAIL  %-20s %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
warn() { printf 'WARN  %-20s %s\n' "$1" "$2"; WARN=$((WARN + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }
value() {
    local key="$1" file="${LOOM_ENV_FILE:-.env}" v
    v="${!key-}"
    if [[ -n "$v" ]]; then
        printf '%s' "$v"
        return
    fi
    [[ -f "$file" ]] || return 0
    awk -v k="$key" '$0 ~ "^[[:space:]]*" k "[[:space:]]*=" {sub("^[[:space:]]*" k "[[:space:]]*=", "", $0); print $0; exit}' "$file"
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf 'Loom Doctor\n===========\n'
[[ -r /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" == fedora ]] && ok OS "Fedora ${VERSION_ID:-unknown}" || warn OS "${PRETTY_NAME:-unknown}; Fedora is first-class"

if have python3 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    ok Python "$(python3 --version)"
else
    bad Python 'Python 3.11+ required'
fi

for c in git curl; do
    if have "$c"; then
        ok "$c" "$(command -v "$c")"
    else
        bad "$c" 'not found'
    fi
done

if have podman; then
    rootless="$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
    if [[ "$rootless" == true ]]; then
        ok Podman 'installed and rootless'
    else
        bad Podman 'installed but rootless mode is unavailable'
    fi
    if podman run --rm quay.io/podman/hello >/dev/null 2>&1; then
        ok 'Podman smoke' 'container execution works'
    else
        bad 'Podman smoke' 'container execution failed'
    fi
else
    bad Podman 'not found'
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON=python3
fi
if "$PYTHON" -c 'import loom_ai' >/dev/null 2>&1; then
    ok Loom 'importable'
else
    bad Loom 'cannot import loom_ai; run ./scripts/install.sh'
fi

storage="$(value LOOM_STORAGE)"
storage="${storage:-memory}"
if [[ "$storage" == postgresql ]]; then
    pg_host="$(value LOOM_PG_HOST)"
    pg_port="$(value LOOM_PG_PORT)"
    pg_host="${pg_host:-localhost}"
    pg_port="${pg_port:-5432}"
    if have pg_isready && pg_isready -h "$pg_host" -p "$pg_port" >/dev/null 2>&1; then
        ok PostgreSQL 'accepting connections'
    else
        bad PostgreSQL 'configured but unavailable'
    fi
else
    warn PostgreSQL "LOOM_STORAGE=$storage"
fi

provider="$(value LOOM_LLM_PROVIDER)"
base="$(value LOOM_LLM_BASE_URL)"
if [[ -n "$provider" && "$provider" != noop && "$base" =~ ^https?://[^/]+ ]]; then
    ok 'LLM provider' 'configured'
else
    bad 'LLM provider' 'real provider and base URL required'
fi

embed="$(value LOOM_EMBEDDING)"
if [[ -n "$embed" && "$embed" != noop && "$embed" != memory ]]; then
    ok Embeddings "$embed"
else
    bad Embeddings 'noop/memory backend is not acceptable for dogfood'
fi

if [[ "$(value LOOM_REQUIRE_GITHUB)" == 1 ]]; then
    if have gh && gh auth status >/dev/null 2>&1; then
        ok 'GitHub CLI' 'authenticated'
    else
        bad 'GitHub CLI' 'required and not authenticated'
    fi
else
    warn 'GitHub CLI' 'not required'
fi

printf '\nSummary: PASS=%d WARN=%d FAIL=%d\n' "$PASS" "$WARN" "$FAIL"
if (( FAIL == 0 )); then
    echo 'RESULT: READY FOR DOGFOOD'
    exit 0
fi
echo 'RESULT: NOT READY'
exit 1
