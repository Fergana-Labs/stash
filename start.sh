#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Stash services locally
# Starts a local pgvector database when DATABASE_URL points
# at localhost:5432 and no database is reachable yet.
# -------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()
# Keep local dev ports aligned with backend defaults and docker compose when free.
DEFAULT_BACKEND_PORT=3456
DEFAULT_FRONTEND_PORT=3457
DEFAULT_COLLAB_PORT=3458
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
    local exit_code="${1:-0}"

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
    exit "$exit_code"
}

trap 'cleanup 0' SIGINT SIGTERM

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
    echo "Loaded environment from .env"
fi

generate_integrations_encryption_key() {
    python - <<'PY'
import base64
import secrets

print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
}

ensure_integrations_encryption_key() {
    if [ -n "${INTEGRATIONS_ENCRYPTION_KEY:-}" ]; then
        return
    fi

    local env_file="$PROJECT_ROOT/.env"
    local generated_key
    local tmp_file

    generated_key="$(generate_integrations_encryption_key)"

    if [ -f "$env_file" ]; then
        tmp_file="$(mktemp)"
        awk -v key="$generated_key" '
            BEGIN { written = 0 }
            /^INTEGRATIONS_ENCRYPTION_KEY=/ {
                if (!written) {
                    print "INTEGRATIONS_ENCRYPTION_KEY=" key
                    written = 1
                }
                next
            }
            { print }
            END {
                if (!written) {
                    print "INTEGRATIONS_ENCRYPTION_KEY=" key
                }
            }
        ' "$env_file" > "$tmp_file"
        mv "$tmp_file" "$env_file"
    else
        printf 'INTEGRATIONS_ENCRYPTION_KEY=%s\n' "$generated_key" > "$env_file"
    fi

    export INTEGRATIONS_ENCRYPTION_KEY="$generated_key"
    echo "[secrets] Generated INTEGRATIONS_ENCRYPTION_KEY in .env."
}

ensure_integrations_encryption_key

export DATABASE_URL="${DATABASE_URL:-$LOCAL_DATABASE_URL}"
BACKEND_PORT="${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"
FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"
COLLAB_PORT="${COLLAB_PORT:-$DEFAULT_COLLAB_PORT}"

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

port_is_free() {
    python - "$1" <<'PY' >/dev/null 2>&1
import errno
import socket
import sys

port = int(sys.argv[1])

for family, host in ((socket.AF_INET6, "::"), (socket.AF_INET, "0.0.0.0")):
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            try:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        sock.bind((host, port))
    except OSError as exc:
        if family == socket.AF_INET6 and exc.errno in {
            errno.EAFNOSUPPORT,
            errno.EADDRNOTAVAIL,
            errno.EPROTONOSUPPORT,
        }:
            continue
        raise
    finally:
        sock.close()
PY
}

find_free_port() {
    local candidate="$1"
    local avoid="${2:-}"

    while [[ ",${avoid}," == *",${candidate},"* ]] || ! port_is_free "$candidate"; do
        candidate=$((candidate + 1))
    done

    echo "$candidate"
}

choose_dev_ports() {
    local requested_backend_port="$BACKEND_PORT"
    local requested_frontend_port="$FRONTEND_PORT"
    local requested_collab_port="$COLLAB_PORT"

    BACKEND_PORT="$(find_free_port "$requested_backend_port")"
    FRONTEND_PORT="$(find_free_port "$requested_frontend_port" "$BACKEND_PORT")"
    COLLAB_PORT="$(find_free_port "$requested_collab_port" "${BACKEND_PORT},${FRONTEND_PORT}")"

    if [ "$BACKEND_PORT" != "$requested_backend_port" ]; then
        echo "[ports]   Backend port ${requested_backend_port} is busy; using ${BACKEND_PORT}."
    fi

    if [ "$FRONTEND_PORT" != "$requested_frontend_port" ]; then
        echo "[ports]   Frontend port ${requested_frontend_port} is busy; using ${FRONTEND_PORT}."
    fi

    if [ "$COLLAB_PORT" != "$requested_collab_port" ]; then
        echo "[ports]   Collab port ${requested_collab_port} is busy; using ${COLLAB_PORT}."
    fi
}

wait_for_services() {
    local pid
    local status

    while true; do
        for pid in "${PIDS[@]}"; do
            if jobs -pr | grep -qx "$pid"; then
                continue
            fi

            if wait "$pid"; then
                status=0
            else
                status=$?
            fi

            echo "[start]  Process ${pid} exited with status ${status}."
            cleanup "$status"
        done

        sleep 1
    done
}

echo "Starting Stash services..."
echo "================================"

# --- Database ---
ensure_local_database

# --- Ports ---
choose_dev_ports

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
PUBLIC_URL="http://localhost:${FRONTEND_PORT}" \
CORS_ORIGINS="http://localhost:${FRONTEND_PORT},http://localhost:${BACKEND_PORT},http://localhost:3000" \
uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
    --proxy-headers --forwarded-allow-ips '*' &
PIDS+=($!)

# --- Collab (Hocuspocus) ---
echo "[collab]   Starting on port ${COLLAB_PORT}..."
cd "$PROJECT_ROOT/collab"
PORT="$COLLAB_PORT" \
BACKEND_URL="http://localhost:${BACKEND_PORT}" \
DATABASE_URL="$DATABASE_URL" \
npm run dev &
PIDS+=($!)

# --- Frontend (Next.js) ---
echo "[frontend] Starting on port ${FRONTEND_PORT}..."
cd "$PROJECT_ROOT/frontend"
BACKEND_INTERNAL_URL="http://localhost:${BACKEND_PORT}" \
NEXT_PUBLIC_COLLAB_URL="ws://localhost:${COLLAB_PORT}" \
PORT="$FRONTEND_PORT" \
npm run dev &
PIDS+=($!)

echo "================================"
echo "All services started. Press Ctrl+C to stop."
echo "  Backend  -> http://localhost:${BACKEND_PORT}"
echo "  Collab   -> ws://localhost:${COLLAB_PORT}"
echo "  Frontend -> http://localhost:${FRONTEND_PORT}"
echo "================================"

# Wait for both app processes; if either exits, stop the other one too.
wait_for_services
