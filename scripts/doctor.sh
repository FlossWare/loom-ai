#!/usr/bin/env bash
set -u
PASS=0; FAIL=0; WARN=0
ok(){ printf 'PASS  %-20s %s\n' "$1" "$2"; PASS=$((PASS+1)); }
bad(){ printf 'FAIL  %-20s %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
warn(){ printf 'WARN  %-20s %s\n' "$1" "$2"; WARN=$((WARN+1)); }
have(){ command -v "$1" >/dev/null 2>&1; }

# Read simple KEY=VALUE config without executing .env.
value(){ local key="$1" file="${LOOM_ENV_FILE:-.env}" v; v="${!key-}"; if [[ -n "$v" ]]; then printf '%s' "$v"; return; fi; [[ -f "$file" ]] || return 0; awk -v k="$key" '$0 ~ "^[[:space:]]*" k "[[:space:]]*=" {sub("^[[:space:]]*" k "[[:space:]]*=", "", $0); print $0; exit}' "$file"; }

printf 'Loom Doctor\n===========\n'
[[ -r /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" == fedora ]] && ok OS "Fedora ${VERSION_ID:-unknown}" || warn OS "${PRETTY_NAME:-unknown}; Fedora is first-class"
if have python3 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then ok Python "$(python3 --version)"; else bad Python 'Python 3.11+ required'; fi
for c in git curl; do have "$c" && ok "$c" "$(command -v "$c")" || bad "$c" 'not found'; done

if have podman; then
  rootless="$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
  [[ "$rootless" == true ]] && ok Podman 'installed and rootless' || bad Podman 'installed but rootless mode is unavailable'
  if podman run --rm quay.io/podman/hello >/dev/null 2>&1; then ok 'Podman smoke' 'container execution works'; else bad 'Podman smoke' 'container execution failed'; fi
else bad Podman 'not found'; fi

if python3 -c 'import loom_ai' >/dev/null 2>&1; then ok Loom 'importable'; else bad Loom 'cannot import loom_ai'; fi
storage="$(value LOOM_STORAGE)"; storage="${storage:-memory}"
if [[ "$storage" == postgresql ]]; then
  if have pg_isready && pg_isready -h "$(value LOOM_PG_HOST)" -p "$(value LOOM_PG_PORT)" >/dev/null 2>&1; then ok PostgreSQL 'accepting connections'; else bad PostgreSQL 'configured but unavailable'; fi
else warn PostgreSQL "LOOM_STORAGE=$storage"; fi
provider="$(value LOOM_LLM_PROVIDER)"; base="$(value LOOM_LLM_BASE_URL)"
if [[ "$provider" == free || "$base" =~ ^https?://[^/]+ ]]; then ok 'LLM provider' 'configured'; else bad 'LLM provider' 'not configured'; fi
embed="$(value LOOM_EMBEDDING)"; [[ "$embed" == openai || "$embed" == litellm ]] && ok Embeddings "$embed" || bad Embeddings 'noop/unsupported backend'
if [[ "$(value LOOM_REQUIRE_GITHUB)" == 1 ]]; then have gh && gh auth status >/dev/null 2>&1 && ok 'GitHub CLI' 'authenticated' || bad 'GitHub CLI' 'required and not authenticated'; else warn 'GitHub CLI' 'not required'; fi

printf '\nSummary: PASS=%d WARN=%d FAIL=%d\n' "$PASS" "$WARN" "$FAIL"
(( FAIL == 0 )) && { echo 'RESULT: READY FOR DOGFOOD'; exit 0; }
echo 'RESULT: NOT READY'; exit 1
