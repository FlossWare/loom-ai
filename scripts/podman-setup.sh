#!/bin/bash
# loom-ai Podman setup — PostgreSQL + pgvector container
#
# Usage: ./scripts/podman-setup.sh
#
# Creates a rootless Podman container for loom-ai's PostgreSQL backend.
# Initializes schema and optionally imports API keys from aio-01.

set -euo pipefail

CONTAINER_NAME="loom-pg"
PG_USER="loom"
PG_PASSWORD="${LOOM_PG_PASSWORD:-loom}"
PG_DATABASE="loom"
PG_PORT="${LOOM_PG_PORT:-5432}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== loom-ai PostgreSQL setup ==="

# Stop existing container if running
if podman container exists "$CONTAINER_NAME" 2>/dev/null; then
    echo "Stopping existing $CONTAINER_NAME..."
    podman stop "$CONTAINER_NAME" 2>/dev/null || true
    podman rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# Create volume for persistence
podman volume create loom-pgdata 2>/dev/null || true

echo "Starting PostgreSQL (pgvector/pgvector:pg16) on port $PG_PORT..."
podman run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_USER="$PG_USER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -e POSTGRES_DB="$PG_DATABASE" \
    -p "${PG_PORT}:5432" \
    -v loom-pgdata:/var/lib/postgresql/data:Z \
    pgvector/pgvector:pg16

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if podman exec "$CONTAINER_NAME" pg_isready -U "$PG_USER" > /dev/null 2>&1; then
        echo "PostgreSQL ready after ${i}s"
        break
    fi
    sleep 1
done

# Run schema init
echo "Initializing schema..."
podman exec -i "$CONTAINER_NAME" psql -U "$PG_USER" -d "$PG_DATABASE" < "$SCRIPT_DIR/init-db.sql"

echo ""
echo "=== loom-ai PostgreSQL ready ==="
echo "  Container: $CONTAINER_NAME"
echo "  Port:      $PG_PORT"
echo "  User:      $PG_USER"
echo "  Database:  $PG_DATABASE"
echo ""
echo "Connection string:"
echo "  postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DATABASE}"
echo ""
echo "To start loom-ai server:"
echo "  LOOM_LLM_PROVIDER=free \\"
echo "  LOOM_PG_HOST=localhost \\"
echo "  LOOM_PG_PORT=$PG_PORT \\"
echo "  LOOM_PG_USER=$PG_USER \\"
echo "  LOOM_PG_PASSWORD=$PG_PASSWORD \\"
echo "  LOOM_PG_DATABASE=$PG_DATABASE \\"
echo "  LOOM_STORAGE=postgresql \\"
echo "  LOOM_SECRETS=postgresql \\"
echo "  LOOM_SEARCH=postgresql \\"
echo "  python -m loom_ai.server"
echo ""
echo "To import API keys from aio-01:"
echo "  ./scripts/import-keys.sh"
