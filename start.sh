#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Octopus services locally
# Assumes: PostgreSQL is already running and npm
#          dependencies are installed.
# -------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()

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

echo "Starting Octopus services..."
echo "================================"

# --- Backend (FastAPI) ---
echo "[backend]  Starting on port 3456..."
cd "$PROJECT_ROOT"
uvicorn backend.main:app --host 0.0.0.0 --port 3456 &
PIDS+=($!)

# --- Frontend (Next.js) ---
echo "[frontend] Starting on port 3000..."
cd "$PROJECT_ROOT/frontend"
PORT=3000 npm run dev &
PIDS+=($!)

echo "================================"
echo "All services started. Press Ctrl+C to stop."
echo "  Backend  -> http://localhost:3456"
echo "  Frontend -> http://localhost:3000"
echo "================================"

# Wait for all background processes
wait
