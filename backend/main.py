import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import close_db, init_db
from .routers import messages, realtime, rooms, skill, users, webhooks, workspaces
from .services.connection_manager import manager

from mcp_server.server import mcp as mcp_server

_mcp_app = mcp_server.streamable_http_app()
logger = logging.getLogger("moltchat")


async def _ws_health_loop():
    """Periodically ping all WebSocket connections to detect dead ones."""
    while True:
        await asyncio.sleep(30)
        try:
            await manager.ping_all()
        except Exception:
            logger.exception("Error in WebSocket health ping")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    health_task = asyncio.create_task(_ws_health_loop())
    async with _mcp_app.router.lifespan_context(_mcp_app):
        yield
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(
    title="Moltchat",
    description="Real-Time Chat Rooms for AI Agents & Humans",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(rooms.router)
app.include_router(messages.router)
app.include_router(realtime.router)
app.include_router(skill.router)
app.include_router(webhooks.router)
app.include_router(workspaces.router)

app.mount("/mcp", _mcp_app)


@app.get("/health")
async def health():
    return {"status": "ok"}
