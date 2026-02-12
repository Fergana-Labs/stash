#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Moltchat services locally
# Assumes: PostgreSQL is already running, Conduit binary
#          is on PATH, and npm dependencies are installed.
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

echo "Starting Moltchat services..."
echo "================================"

# --- Backend (FastAPI) ---
echo "[backend]  Starting on port 3456..."
cd "$PROJECT_ROOT/backend"
uvicorn backend.main:app --host 0.0.0.0 --port 3456 &
PIDS+=($!)

# --- Frontend (Next.js) ---
echo "[frontend] Starting on port 3457..."
cd "$PROJECT_ROOT/frontend"
npm run dev &
PIDS+=($!)

# --- Conduit (Matrix homeserver) ---
echo "[conduit]  Starting on port 6167..."
CONDUIT_CONFIG="$PROJECT_ROOT/conduit/conduit.toml" conduit &
PIDS+=($!)

# --- Bridge (Matrix relay bot) ---
echo "[bridge]   Starting relay bot..."
cd "$PROJECT_ROOT/bridge"
python -m bridge.relay &
PIDS+=($!)

echo "================================"
echo "All services started. Press Ctrl+C to stop."
echo "  Backend  -> http://localhost:3456"
echo "  Frontend -> http://localhost:3457"
echo "  Conduit  -> http://localhost:6167"
echo "================================"

# Wait for all background processes
wait
