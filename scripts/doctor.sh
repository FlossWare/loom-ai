#!/usr/bin/env bash
set -u

# Loom environment health check. This script diagnoses; it does not install.
# It is intentionally conservative: required failures produce a non-zero exit.

PASS=0
FAIL=0
WARN=0

ok() { printf 'PASS  %-22s %s\n' "$1" "$2"; PASS=$((PASS + 1)); }
bad() { printf 'FAIL  %-22s %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
warn() { printf 'WARN  %-22s %s\n' "$1" "$2"; WARN=$((WARN + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

# Read only simple KEY=VALUE assignments from .env. Do not source the file:
# doctor is a diagnostic and must not execute arbitrary shell code from config.
env_file_value() {
  local key="$1" file="$2" value
  [[ -f "$file" ]] || return 1
  value="$(awk -v key="$key" '
    $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      sub("^[[:space:]]*" key "[[:space:]]*=", "", $0)
      print $0
      exit
    }
  ' "$file")"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s\n' "$value"
}

# Environment variables take precedence. If they are absent, read known values
# from the repository .env without executing it.
CONFIG_FILE="${LOOM_ENV_FILE:-.env}"
config_or_env() {
  local key="$1" current
  current="${!key-}"
  if [[ -n "$current" ]]; then
    printf '%s\n' "$current"
  elif [[ -f "$CONFIG_FILE" ]]; then
    env_file_value "$key" "$CONFIG_FILE" || true
  fi
}

LOOM_STORAGE_VALUE="$(config_or_env LOOM_STORAGE)"
LOOM_QUEUE_VALUE="$(config_or_env LOOM_QUEUE)"
LOOM_PROVIDER_VALUE="$(config_or_env LOOM_LLM_PROVIDER)"
LOOM_BASE_URL_VALUE="$(config_or_env LOOM_LLM_BASE_URL)"
LOOM_EMBED_VALUE="$(config_or_env LOOM_EMBEDDING)"
LOOM_REQUIRE_GITHUB_VALUE="$(config_or_env LOOM_REQUIRE_GITHUB)"
LOOM_PG_HOST_VALUE="$(config_or_env LOOM_PG_HOST)"
LOOM_PG_PORT_VALUE="$(config_or_env LOOM_PG_PORT)"
LOOM_REDIS_HOST_VALUE="$(config_or_env LOOM_REDIS_HOST)"
LOOM_REDIS_PORT_VALUE="$(config_or_env LOOM_REDIS_PORT)"

printf 'Loom Doctor\n===========\n\n'

# OS
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" == "fedora" ]]; then
    ok "OS" "Fedora ${VERSION_ID:-unknown}"
  else
    warn "OS" "${PRETTY_NAME:-unknown}; Fedora is the first supported Linux target"
  fi
else
  bad "OS" "cannot identify operating system"
fi

# Python
if have python3; then
  PYVER="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true)"
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    ok "Python" "$PYVER"
  else
    bad "Python" "Python >= 3.11 required; found ${PYVER:-unknown}"
  fi
else
  bad "Python" "python3 not found"
fi

# Core tools
for cmd in git curl; do
  if have "$cmd"; then
    ok "$cmd" "$(command -v "$cmd")"
  else
    bad "$cmd" "not found"
  fi
done

# GitHub CLI is required only for GitHub-backed publication workflows.
if [[ "${LOOM_REQUIRE_GITHUB_VALUE:-0}" == "1" ]]; then
  if have gh; then
    if gh auth status >/dev/null 2>&1; then
      ok "GitHub CLI" "installed and authenticated"
    else
      bad "GitHub CLI" "installed but not authenticated"
    fi
  else
    bad "GitHub CLI" "gh not found"
  fi
else
  if have gh; then
    ok "GitHub CLI" "installed; not required by current configuration"
  else
    warn "GitHub CLI" "not installed; set LOOM_REQUIRE_GITHUB=1 for GitHub-backed dogfood"
  fi
fi

# Loom import/environment
if python3 -c 'import loom_ai' >/dev/null 2>&1; then
  ok "Loom" "importable"
else
  bad "Loom" "cannot import loom_ai; run install/setup first"
fi

# PostgreSQL: only required when configured as the storage backend.
STORAGE="${LOOM_STORAGE_VALUE:-memory}"
if [[ "$STORAGE" == "postgresql" ]]; then
  PGHOST="${LOOM_PG_HOST_VALUE:-localhost}"
  PGPORT="${LOOM_PG_PORT_VALUE:-5432}"
  if have pg_isready; then
    if pg_isready -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1; then
      ok "PostgreSQL" "$PGHOST:$PGPORT accepting connections"
    else
      bad "PostgreSQL" "$PGHOST:$PGPORT not accepting connections"
    fi
  else
    bad "PostgreSQL" "pg_isready not found"
  fi
else
  warn "PostgreSQL" "LOOM_STORAGE=${STORAGE}; not required by current configuration"
fi

# Redis: only required for the Redis queue backend.
QUEUE="${LOOM_QUEUE_VALUE:-memory}"
if [[ "$QUEUE" == "redis" ]]; then
  RHOST="${LOOM_REDIS_HOST_VALUE:-localhost}"
  RPORT="${LOOM_REDIS_PORT_VALUE:-6379}"
  if have redis-cli; then
    if redis-cli -h "$RHOST" -p "$RPORT" ping 2>/dev/null | grep -q '^PONG$'; then
      ok "Redis" "$RHOST:$RPORT responding"
    else
      bad "Redis" "$RHOST:$RPORT not responding"
    fi
  else
    bad "Redis" "redis-cli not found"
  fi
else
  warn "Redis" "LOOM_QUEUE=${QUEUE}; not required by current configuration"
fi

# LLM configuration. Do not print credentials.
PROVIDER="${LOOM_PROVIDER_VALUE:-openai-compatible}"
BASE_URL="${LOOM_BASE_URL_VALUE:-}"
if [[ "$PROVIDER" == "free" ]]; then
  ok "LLM provider" "FreeModelRouter configured"
elif [[ -n "$BASE_URL" ]]; then
  if [[ "$BASE_URL" =~ ^https?://[^/]+ ]]; then
    ok "LLM provider" "$PROVIDER configured"
  else
    bad "LLM provider" "LOOM_LLM_BASE_URL is not a valid HTTP(S) URL"
  fi
else
  bad "LLM provider" "LOOM_LLM_BASE_URL is not configured"
fi

# Embedding backend. Noop is not acceptable for persistent dogfood.
EMBED="${LOOM_EMBED_VALUE:-noop}"
if [[ "$EMBED" == "noop" ]]; then
  bad "Embeddings" "noop embeddings are not valid for dogfood"
elif [[ "$EMBED" == "openai" || "$EMBED" == "litellm" ]]; then
  ok "Embeddings" "$EMBED configured"
else
  bad "Embeddings" "unsupported backend: $EMBED"
fi

# Workspace permissions and repository state.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$ROOT" ]]; then
  if [[ -w "$ROOT" ]]; then
    ok "Workspace" "$ROOT writable"
  else
    bad "Workspace" "$ROOT is not writable"
  fi
  if [[ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]]; then
    ok "Git workspace" "clean"
  else
    warn "Git workspace" "has uncommitted changes; publication should use an isolated worktree"
  fi
else
  bad "Workspace" "not inside a Git repository"
fi

if [[ -f "$CONFIG_FILE" ]]; then
  ok "Configuration" "$CONFIG_FILE present"
else
  warn "Configuration" "no $CONFIG_FILE; environment variables may still be configured"
fi

printf '\nSummary\n-------\nPASS: %d  WARN: %d  FAIL: %d\n' "$PASS" "$WARN" "$FAIL"
if (( FAIL > 0 )); then
  printf 'RESULT: NOT READY\n'
  exit 1
fi
printf 'RESULT: READY FOR DOGFOOD\n'
