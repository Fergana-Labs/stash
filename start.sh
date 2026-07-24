#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------
# start.sh — Start all Stash services locally:
# database, redis, backend, celery worker, celery beat,
# collab, and frontend.
# Each worktree gets its own pgvector database and redis
# containers, created on demand and garbage-collected
# after the worktree is deleted. Set DATABASE_URL /
# REDIS_URL to use your own instances instead.
# -------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()
# The frontend type-check watcher is advisory: tracked outside PIDS so its
# exit never takes down the stack, but cleaned up with everything else.
TSC_WATCH_PID=""
DEV_DB_IMAGE="pgvector/pgvector:pg16"
# Containers carry this label (set to the absolute worktree path) so databases
# of deleted worktrees can be garbage-collected on every start.
DEV_DB_WORKTREE_LABEL="ai.joinstash.dev-db-worktree"
# Short path hash so worktrees with the same directory name don't collide.
DEV_DB_CONTAINER="stash-dev-pg-$(basename "$PROJECT_ROOT")-$(printf '%s' "$PROJECT_ROOT" | shasum | cut -c1-6)"
DEV_DB_VOLUME="${DEV_DB_CONTAINER}-data"
DEV_DB_USER="stash"
DEV_DB_PASSWORD="stash"
DEV_DB_NAME="stash"
STARTED_DEV_DB=false
DEV_REDIS_IMAGE="redis:7-alpine"
DEV_REDIS_CONTAINER="stash-dev-redis-$(basename "$PROJECT_ROOT")-$(printf '%s' "$PROJECT_ROOT" | shasum | cut -c1-6)"
STARTED_DEV_REDIS=false

kill_tree() {
    local pid="$1"
    local child
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill -9 "$pid" 2>/dev/null || true
}

cleanup() {
    local exit_code="${1:-0}"

    echo ""
    echo "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    if [ -n "$TSC_WATCH_PID" ]; then
        kill "$TSC_WATCH_PID" 2>/dev/null || true
    fi
    # Bounded wait, then force-kill: celery's warm shutdown can wedge on a
    # stuck pool process, and a hung child must not block Ctrl+C forever.
    for _ in {1..15}; do
        if ! jobs -pr | grep -q .; then
            break
        fi
        sleep 1
    done
    for pid in "${PIDS[@]}"; do
        kill_tree "$pid"
    done
    if [ -n "$TSC_WATCH_PID" ]; then
        kill_tree "$TSC_WATCH_PID"
    fi
    wait 2>/dev/null
    if [ "$STARTED_DEV_DB" = "true" ]; then
        echo "[db]      Stopping dev database container..."
        docker stop "$DEV_DB_CONTAINER" >/dev/null 2>&1 || true
    fi
    if [ "$STARTED_DEV_REDIS" = "true" ]; then
        echo "[redis]   Stopping dev redis container..."
        docker stop "$DEV_REDIS_CONTAINER" >/dev/null 2>&1 || true
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

ensure_python_deps() {
    if python -c 'import uvicorn, alembic, asyncpg, celery, redis' >/dev/null 2>&1; then
        return
    fi

    if ! command -v uv >/dev/null 2>&1; then
        echo "[deps]    Python dependencies are missing and uv is not installed."
        echo "[deps]    Install uv (https://docs.astral.sh/uv/), then rerun ./start.sh."
        exit 1
    fi

    if [ -z "${VIRTUAL_ENV:-}" ]; then
        if [ ! -d "$PROJECT_ROOT/.venv" ]; then
            echo "[deps]    Creating Python virtualenv at .venv..."
            uv venv -p 3.12 "$PROJECT_ROOT/.venv"
        fi
        # shellcheck disable=SC1091
        source "$PROJECT_ROOT/.venv/bin/activate"
    fi

    echo "[deps]    Installing backend Python dependencies..."
    uv pip install -r "$PROJECT_ROOT/backend/requirements.txt" -r "$PROJECT_ROOT/backend/requirements-dev.txt"
}

ensure_node_deps() {
    local dir
    for dir in frontend collab; do
        # Reinstall when node_modules is missing or the lockfile changed since
        # the last install (npm ci recreates node_modules, refreshing its mtime).
        if [ ! -d "$PROJECT_ROOT/$dir/node_modules" ] || \
           [ "$PROJECT_ROOT/$dir/package-lock.json" -nt "$PROJECT_ROOT/$dir/node_modules" ]; then
            echo "[deps]    Installing $dir dependencies..."
            (cd "$PROJECT_ROOT/$dir" && npm ci)
        fi
    done
}

# App ports are fixed, not configurable: OAuth redirect URIs registered with
# providers (Google, Linear, GitHub, ...) point at the backend on 3456, so a
# stack on any other port has silently broken integrations. One local stack
# per machine; if a port is taken, we fail loud instead of shifting.
BACKEND_PORT=3456
FRONTEND_PORT=3457
COLLAB_PORT=3458

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

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[docker]  Docker is required for the local dev database and redis."
        echo "[docker]  Install Docker Desktop, then rerun ./start.sh."
        exit 1
    fi

    if docker info >/dev/null 2>&1; then
        return
    fi

    if [ "$(uname)" = "Darwin" ]; then
        echo "[docker]  Docker daemon is not running; starting Docker Desktop..."
        open -a Docker
        for _ in {1..60}; do
            if docker info >/dev/null 2>&1; then
                echo "[docker]  Docker daemon is ready."
                return
            fi
            sleep 1
        done
    fi

    echo "[docker]  Docker daemon is not running and did not come up."
    echo "[docker]  Start it manually, then rerun ./start.sh."
    exit 1
}

container_exists() {
    docker container inspect "$DEV_DB_CONTAINER" >/dev/null 2>&1
}

container_is_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$DEV_DB_CONTAINER" 2>/dev/null)" = "true" ]
}

remove_orphaned_dev_containers() {
    docker ps -a --filter "label=$DEV_DB_WORKTREE_LABEL" \
        --format "{{.Names}} {{.Label \"$DEV_DB_WORKTREE_LABEL\"}}" |
    while read -r container worktree; do
        if [ ! -d "$worktree" ]; then
            echo "[docker]  Removing dev container of deleted worktree ${worktree}..."
            docker rm -f "$container" >/dev/null
            docker volume rm "${container}-data" >/dev/null 2>&1 || true
        fi
    done
}

dev_db_host_port() {
    docker inspect -f '{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostPort}}' "$DEV_DB_CONTAINER"
}

ensure_local_database() {
    # An explicit DATABASE_URL means the caller owns the database; never
    # substitute a local container for it.
    if [ -n "${DATABASE_URL:-}" ]; then
        if database_is_ready; then
            echo "[db]      Using DATABASE_URL from the environment."
            return
        fi
        echo "[db]      DATABASE_URL is set but not reachable."
        echo "[db]      Start that database (or unset DATABASE_URL for a local dev container), then rerun ./start.sh."
        exit 1
    fi

    ensure_docker
    remove_orphaned_dev_containers

    # The host port is baked in at creation time, and another process can grab
    # it while the container is stopped. Recreate the container on a fresh port
    # in that case; the data volume is separate and survives.
    if container_exists && ! container_is_running && ! port_is_free "$(dev_db_host_port)"; then
        echo "[db]      Host port $(dev_db_host_port) was taken while the container was stopped; recreating it on a free port..."
        docker rm "$DEV_DB_CONTAINER" >/dev/null
    fi

    if container_exists; then
        if container_is_running; then
            echo "[db]      This worktree's dev database container is already running."
        else
            echo "[db]      Starting this worktree's dev database container..."
            docker start "$DEV_DB_CONTAINER" >/dev/null
            STARTED_DEV_DB=true
        fi
    else
        echo "[db]      Creating a dev database container for this worktree..."
        docker run -d \
            --name "$DEV_DB_CONTAINER" \
            --label "${DEV_DB_WORKTREE_LABEL}=${PROJECT_ROOT}" \
            -e POSTGRES_USER="$DEV_DB_USER" \
            -e POSTGRES_PASSWORD="$DEV_DB_PASSWORD" \
            -e POSTGRES_DB="$DEV_DB_NAME" \
            -p "$(find_free_port 5432):5432" \
            -v "$DEV_DB_VOLUME:/var/lib/postgresql/data" \
            "$DEV_DB_IMAGE" >/dev/null
        STARTED_DEV_DB=true
    fi

    export DATABASE_URL="postgresql://${DEV_DB_USER}:${DEV_DB_PASSWORD}@localhost:$(dev_db_host_port)/${DEV_DB_NAME}"

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

redis_is_ready() {
    python - <<'PY' >/dev/null 2>&1
import os

import redis

redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2).ping()
PY
}

ensure_local_redis() {
    # An explicit REDIS_URL means the caller owns redis; never substitute a
    # local container for it.
    if [ -n "${REDIS_URL:-}" ]; then
        if redis_is_ready; then
            echo "[redis]   Using REDIS_URL from the environment."
            return
        fi
        echo "[redis]   REDIS_URL is set but not reachable."
        echo "[redis]   Start that redis (or unset REDIS_URL for a local dev container), then rerun ./start.sh."
        exit 1
    fi

    ensure_docker

    # The broker and result store are disposable in dev, so recreate the
    # container fresh each run instead of managing stopped-container state.
    docker rm -f "$DEV_REDIS_CONTAINER" >/dev/null 2>&1 || true

    echo "[redis]   Creating a dev redis container for this worktree..."
    local redis_port
    redis_port="$(find_free_port 6379)"
    docker run -d --rm \
        --name "$DEV_REDIS_CONTAINER" \
        --label "${DEV_DB_WORKTREE_LABEL}=${PROJECT_ROOT}" \
        -p "${redis_port}:6379" \
        "$DEV_REDIS_IMAGE" >/dev/null
    STARTED_DEV_REDIS=true

    export REDIS_URL="redis://localhost:${redis_port}/0"

    echo "[redis]   Waiting for Redis..."
    for _ in {1..30}; do
        if redis_is_ready; then
            echo "[redis]   Redis is ready."
            return
        fi
        sleep 1
    done

    echo "[redis]   Dev redis did not become ready in time."
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

    while ! port_is_free "$candidate"; do
        candidate=$((candidate + 1))
    done

    echo "$candidate"
}

ensure_app_ports_free() {
    local port pid cmd cwd
    for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$COLLAB_PORT"; do
        if port_is_free "$port"; then
            continue
        fi

        # lsof exits nonzero when it finds nothing (e.g. the holder just
        # exited); with pipefail that must not kill the script mid-message.
        pid="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
        if [ -z "$pid" ]; then
            echo "[ports]   Port ${port} is in use, but the holder could not be identified"
            echo "[ports]   (it may have just exited). Rerun ./start.sh."
            exit 1
        fi

        cmd="$(ps -o command= -p "$pid" 2>/dev/null | cut -c1-120 || true)"
        cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1 || true)"

        echo "[ports]   Port ${port} is held by pid ${pid}: ${cmd:-unknown command}"
        echo "[ports]   started from: ${cwd:-unknown}"
        if [ "$cwd" = "$PROJECT_ROOT" ] || [[ "$cwd" == "$PROJECT_ROOT"/* ]]; then
            echo "[ports]   That process belongs to THIS checkout — you already have a stack (or part"
            echo "[ports]   of one) running here. Use it, or stop it (kill ${pid}) and rerun ./start.sh."
        else
            echo "[ports]   App ports are fixed (backend ${BACKEND_PORT}, frontend ${FRONTEND_PORT}, collab ${COLLAB_PORT}); OAuth"
            echo "[ports]   redirect URIs are registered against them, so nothing may run elsewhere."
            echo "[ports]   One local stack at a time. If that process is another checkout's live"
            echo "[ports]   stack, wait your turn; only kill ${pid} if you know it's abandoned."
        fi
        exit 1
    done
}

# Next.js allows one dev server per checkout: `next dev` holds an exclusive
# flock on frontend/.next/dev/lock, and a second one exits at startup. Without
# a preflight check that failure happens last — after the database, backend,
# and collab are already up — and tears the whole stack down on the way out.

frontend_dev_server_info() {
    # Prints "<pid> <appUrl>" if a live dev server holds the lock, else nothing.
    # Probes the same flock Next takes, so a crashed server's leftover lock
    # file (the OS releases its flock) never counts as running.
    python - "$PROJECT_ROOT/frontend/.next/dev/lock" <<'PY'
import fcntl
import json
import sys

try:
    f = open(sys.argv[1])
except OSError:
    sys.exit(0)

with f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.exit(0)
    except OSError:
        pass
    try:
        info = json.load(f)
    except ValueError:
        info = {}
    print(info.get("pid", "unknown"), info.get("appUrl", "unknown"))
PY
}

ensure_frontend_dev_server_not_running() {
    local info pid app_url
    info="$(frontend_dev_server_info)"
    if [ -z "$info" ]; then
        return
    fi

    pid="${info%% *}"
    app_url="${info#* }"

    if [ "${START_KILL_DEV_SERVER:-0}" = "1" ] && [ "$pid" != "unknown" ]; then
        echo "[frontend] Stopping the dev server already running for this worktree (pid ${pid})..."
        kill "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            if [ -z "$(frontend_dev_server_info)" ]; then
                return
            fi
            sleep 0.5
        done
        echo "[frontend] The dev server (pid ${pid}) did not exit; stop it manually, then rerun ./start.sh."
        exit 1
    fi

    echo "[frontend] This checkout already has a dev server at ${app_url} (pid ${pid}) —"
    echo "[frontend] started here, possibly by another terminal or agent session."
    echo "[frontend] Use it, stop it (kill ${pid}), or rerun with START_KILL_DEV_SERVER=1 to replace it."
    exit 1
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

# --- Preflight ---
ensure_frontend_dev_server_not_running
ensure_app_ports_free

# --- Dependencies ---
ensure_python_deps
ensure_node_deps

# --- Database ---
ensure_local_database

# --- Redis ---
ensure_local_redis

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

# --- Celery worker + beat ---
# Same commands as docker-compose.prod.yml; beat must run as exactly one instance.
echo "[worker]   Starting celery worker..."
celery -A backend.celery_app worker --loglevel=info --concurrency=4 &
PIDS+=($!)

echo "[beat]     Starting celery beat..."
celery -A backend.celery_app beat --loglevel=info \
    --schedule "$PROJECT_ROOT/.celerybeat-schedule" &
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

# --- Frontend type-check watcher ---
# `next dev` compiles with SWC and never type-checks, so a type error that
# fails `next build` (and therefore CI and the prod deploy) stays invisible
# during dev. The watcher streams those errors into this terminal as you edit.
echo "[types]    Starting frontend type-check watcher..."
npx tsc --noEmit --watch --preserveWatchOutput &
TSC_WATCH_PID=$!

echo "================================"
echo "All services started. Press Ctrl+C to stop."
echo "  Backend  -> http://localhost:${BACKEND_PORT}"
echo "  Collab   -> ws://localhost:${COLLAB_PORT}"
echo "  Frontend -> http://localhost:${FRONTEND_PORT}"
echo "  Database -> ${DATABASE_URL}"
echo "  Redis    -> ${REDIS_URL}"
echo "================================"

# Wait for both app processes; if either exits, stop the other one too.
wait_for_services
