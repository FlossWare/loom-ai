#!/bin/bash
# Import PERSONAL_* API keys from aio-01 into loom-ai's local PostgreSQL
#
# Usage: ./scripts/import-keys.sh [aio-01-dsn]
#
# Reads keys from aio-01's auth.secrets and inserts into local loom container.

set -euo pipefail

SOURCE_DSN="${1:-postgresql://redhat_orchestrator:rh-orch-2026-laptop02@aio-01:5433/learning}"
CONTAINER_NAME="loom-pg"
PG_USER="${LOOM_PG_USER:-loom}"
PG_DATABASE="${LOOM_PG_DATABASE:-loom}"

echo "=== Importing API keys from aio-01 ==="

# Extract keys from source
KEYS=$(psql "$SOURCE_DSN" -t -A -F $'\t' -c \
    "SELECT key, value FROM auth.secrets WHERE encrypted = false AND key LIKE 'PERSONAL_%API_KEY%' ORDER BY key" 2>/dev/null)

if [ -z "$KEYS" ]; then
    echo "No keys found or cannot connect to source database."
    echo "Make sure you can reach aio-01:5433."
    exit 1
fi

COUNT=0
while IFS=$'\t' read -r key value; do
    [ -z "$key" ] && continue
    podman exec -i "$CONTAINER_NAME" psql -U "$PG_USER" -d "$PG_DATABASE" -c \
        "INSERT INTO auth.secrets (key, value) VALUES ('$key', '$value') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value" \
        > /dev/null 2>&1
    COUNT=$((COUNT + 1))
    echo "  Imported: $key"
done <<< "$KEYS"

echo ""
echo "Imported $COUNT API keys into loom-pg"
