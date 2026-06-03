#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Stash services locally
# Starts a local pgvector database when DATABASE_URL points
# at localhost:5432 and no database is reachable yet.
# -------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()
# Keep local dev ports aligned with backend defaults and docker compose.
BACKEND_PORT=3456
FRONTEND_PORT=3457
LOCAL_DATABASE_URL="postgresql://stash:stash@localhost:5432/stash"
DEV_DB_CONTAINER="stash-dev-postgres"
DEV_DB_IMAGE="pgvector/pgvector:pg16"
DEV_DB_VOLUME="stash_dev_postgres_data"
DEV_DB_USER="stash"
DEV_DB_PASSWORD="stash"
DEV_DB_NAME="stash"
DEV_DB_PORT="5432"
STARTED_DEV_DB=false

cleanup() {
    echo ""
    echo "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    if [ "$STARTED_DEV_DB" = "true" ]; then
        echo "[db]      Stopping dev database container..."
        docker stop "$DEV_DB_CONTAINER" >/dev/null 2>&1 || true
    fi
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
    echo "Loaded environment from .env"
fi

export DATABASE_URL="${DATABASE_URL:-$LOCAL_DATABASE_URL}"

database_is_ready() {
    python - <<'PY' >/dev/null 2>&1
import asyncio
import os

import asyncpg


async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=2)
    await conn.close()


asyncio.run(main())
PY
}

uses_local_dev_database() {
    case "$DATABASE_URL" in
        postgresql://*@localhost:5432/*|postgresql://*@127.0.0.1:5432/*|postgres://*@localhost:5432/*|postgres://*@127.0.0.1:5432/*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

container_exists() {
    docker container inspect "$DEV_DB_CONTAINER" >/dev/null 2>&1
}

container_is_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$DEV_DB_CONTAINER" 2>/dev/null)" = "true" ]
}

ensure_local_database() {
    if database_is_ready; then
        echo "[db]      PostgreSQL is reachable."
        return
    fi

    if ! uses_local_dev_database; then
        echo "[db]      DATABASE_URL is not reachable."
        echo "[db]      Start the configured database, then rerun ./start.sh."
        exit 1
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo "[db]      Docker is required to start the local dev database."
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "[db]      Docker is installed, but the daemon is not running."
        exit 1
    fi

    if container_exists; then
        if container_is_running; then
            echo "[db]      Dev database container is already running."
        else
            echo "[db]      Starting existing dev database container..."
            docker start "$DEV_DB_CONTAINER" >/dev/null
            STARTED_DEV_DB=true
        fi
    else
        echo "[db]      Creating dev database container..."
        if ! docker run -d \
            --name "$DEV_DB_CONTAINER" \
            -e POSTGRES_USER="$DEV_DB_USER" \
            -e POSTGRES_PASSWORD="$DEV_DB_PASSWORD" \
            -e POSTGRES_DB="$DEV_DB_NAME" \
            -p "$DEV_DB_PORT:5432" \
            -v "$DEV_DB_VOLUME:/var/lib/postgresql/data" \
            "$DEV_DB_IMAGE" >/dev/null; then
            echo "[db]      Failed to start the dev database container."
            echo "[db]      Check whether port ${DEV_DB_PORT} is already in use."
            exit 1
        fi
        STARTED_DEV_DB=true
    fi

    echo "[db]      Waiting for PostgreSQL..."
    for _ in {1..60}; do
        if database_is_ready; then
            echo "[db]      PostgreSQL is ready."
            return
        fi
        sleep 1
    done

    echo "[db]      Dev database did not become ready in time."
    exit 1
}

echo "Starting Stash services..."
echo "================================"

# --- Database ---
ensure_local_database

# --- Migrations ---
cd "$PROJECT_ROOT"
echo "[migrate]  Running OSS migrations..."
alembic upgrade head

if [ "${AUTH0_ENABLED:-false}" = "true" ]; then
    echo "[migrate]  Running managed migrations..."
    alembic -c backend/managed/alembic.ini upgrade head
fi

# --- Backend (FastAPI) ---
echo "[backend]  Starting on port ${BACKEND_PORT}..."
uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
    --proxy-headers --forwarded-allow-ips '*' &
PIDS+=($!)

# --- Frontend (Next.js) ---
echo "[frontend] Starting on port ${FRONTEND_PORT}..."
cd "$PROJECT_ROOT/frontend"
PORT="$FRONTEND_PORT" npm run dev &
PIDS+=($!)

echo "================================"
echo "All services started. Press Ctrl+C to stop."
echo "  Backend  -> http://localhost:${BACKEND_PORT}"
echo "  Frontend -> http://localhost:${FRONTEND_PORT}"
echo "================================"

# Wait for all background processes
wait
