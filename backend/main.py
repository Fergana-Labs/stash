import logging
from contextlib import asynccontextmanager

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
    aggregate, files, memory, notebooks, skill, tables, users,
    workspaces,
)

from mcp_server.server import mcp as mcp_server

_mcp_app = mcp_server.streamable_http_app()
logger = logging.getLogger("octopus")


class _TrailingSlashMiddleware:
    """Rewrite /mcp to /mcp/ so Starlette Mount doesn't 307-redirect."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with _mcp_app.router.lifespan_context(_mcp_app):
        yield
    await close_db()


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


app = FastAPI(
    title="Octopus",
    description="Shared memory for AI agents",
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
app.include_router(workspaces.router)
app.include_router(notebooks.ws_router)
app.include_router(notebooks.personal_router)
app.include_router(memory.ws_router)
app.include_router(memory.personal_router)
app.include_router(tables.ws_router)
app.include_router(tables.personal_router)
app.include_router(files.ws_router)
app.include_router(files.personal_router)
app.include_router(aggregate.router)
app.include_router(skill.router)

app.mount("/mcp", _mcp_app)


@app.get("/health")
async def health():
    return {"status": "ok"}
