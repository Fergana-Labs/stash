#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Stash services locally
# Assumes: PostgreSQL is already running and npm
#          dependencies are installed.
# -------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()
# Keep local dev ports aligned with backend defaults and docker compose.
BACKEND_PORT=3456
FRONTEND_PORT=3457

cleanup() {
    echo ""
    echo "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
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

echo "Starting Stash services..."
echo "================================"

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
