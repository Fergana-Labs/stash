import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings
from .database import close_db, init_db
from .middleware import limiter
from .routers import (
    personas, aggregate, chats, deck_viewer, decks, dms, documents, files,
    memory, notebooks, realtime, search, skill, tables, users, webhooks,
    workspaces,
)
from .services.connection_manager import manager

from mcp_server.server import mcp as mcp_server

_mcp_app = mcp_server.streamable_http_app()
logger = logging.getLogger("boozle")


class _TrailingSlashMiddleware:
    """Rewrite /mcp to /mcp/ so Starlette Mount doesn't 307-redirect."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


async def _ws_health_loop():
    """Periodically ping all WebSocket connections to detect dead ones."""
    while True:
        await asyncio.sleep(30)
        try:
            await manager.ping_all()
        except Exception:
            logger.exception("Error in WebSocket health ping")


async def _sleep_agent_loop():
    """Periodically run sleep agent curation for all enabled agents."""
    from .services import sleep_service
    while True:
        await asyncio.sleep(settings.SLEEP_AGENT_CHECK_INTERVAL)
        if not settings.SLEEP_AGENT_ENABLED:
            continue
        try:
            agents = await sleep_service.get_due_agents()
            for agent_id in agents:
                try:
                    await sleep_service.curate(agent_id)
                except Exception:
                    logger.exception("Sleep agent failed for %s", agent_id)
        except Exception:
            logger.exception("Sleep agent loop error")


async def _webhook_delivery_loop():
    """Poll webhook_deliveries table and dispatch pending items."""
    from .services import webhook_service
    while True:
        await asyncio.sleep(5)
        try:
            await webhook_service.process_pending_deliveries()
        except Exception:
            logger.exception("Webhook delivery loop error")


def _make_pg_notify_callback(loop: asyncio.AbstractEventLoop):
    """Return an asyncpg LISTEN callback that dispatches to local connections.

    asyncpg fires notification callbacks synchronously on the event loop, so
    we use loop.create_task() (not run_coroutine_threadsafe, which is for
    cross-thread scheduling and returns an unchecked Future).
    """
    import json
    from uuid import UUID

    def _callback(conn, pid, channel, payload):
        try:
            data = json.loads(payload)
            room_id = UUID(data["room_id"])
            message = data["message"]
            loop.create_task(manager.broadcast_local(room_id, message))
        except Exception:
            logger.exception("pg_notify callback error")

    return _callback


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Dedicated connection for Postgres LISTEN/NOTIFY (cannot use the pool)
    notify_conn = await asyncpg.connect(settings.DATABASE_URL)
    loop = asyncio.get_running_loop()
    notify_cb = _make_pg_notify_callback(loop)
    await notify_conn.add_listener("boozle_events", notify_cb)

    health_task = asyncio.create_task(_ws_health_loop())
    sleep_task = asyncio.create_task(_sleep_agent_loop())
    delivery_task = asyncio.create_task(_webhook_delivery_loop())

    async with _mcp_app.router.lifespan_context(_mcp_app):
        yield

    for task in (health_task, sleep_task, delivery_task):
        task.cancel()
    for task in (health_task, sleep_task, delivery_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    await notify_conn.remove_listener("boozle_events", notify_cb)
    await notify_conn.close()
    await close_db()


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


app = FastAPI(
    title="Boozle",
    description="Real-Time Chat Rooms for AI Agents & Humans",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(_TrailingSlashMiddleware)

app.include_router(users.router)
app.include_router(personas.router)
app.include_router(workspaces.router)
app.include_router(chats.ws_router)
app.include_router(chats.personal_router)
app.include_router(notebooks.ws_router)
app.include_router(notebooks.personal_router)
app.include_router(memory.ws_router)
app.include_router(memory.personal_router)
app.include_router(realtime.router)
app.include_router(dms.router)
app.include_router(decks.ws_router)
app.include_router(decks.personal_router)
app.include_router(deck_viewer.router)
app.include_router(tables.ws_router)
app.include_router(tables.personal_router)
app.include_router(files.ws_router)
app.include_router(files.personal_router)
app.include_router(documents.ws_router)
app.include_router(search.ws_router)
app.include_router(search.personal_router)
app.include_router(aggregate.router)
app.include_router(webhooks.router)
app.include_router(skill.router)

app.mount("/mcp", _mcp_app)


@app.get("/health")
async def health():
    return {"status": "ok"}
