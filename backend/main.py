import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from . import exports as _exports  # noqa: F401 — registers exporter Celery tasks
from . import integrations as _integrations  # noqa: F401 — registers providers + importers
from .config import settings
from .database import close_db, init_db
from .integrations.router import router as integrations_router
from .middleware import limiter
from .routers import (
    admin,
    agent_chat,
    aggregate,
    analytics,
    batch,
    cartridge_invites,
    cartridges,
    collab,
    demo,
    discover,
    exports,
    files,
    files_tree,
    marketing,
    memory,
    pins,
    publish,
    security_audit,
    session_folders,
    sessions,
    shares,
    skill,
    sources,
    tables,
    tasks,
    transcripts,
    trash,
    users,
    webhooks,
    workspace_knowledge,
    workspaces,
)
from .services import demo_service
from .services.row_validation import RowValidationError

logger = logging.getLogger("stash")

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background workers (file extraction, embedding reconcile, viz
    # precompute, session summarizer) now run in the Celery `worker` and
    # `beat` services — see backend/celery_app.py.
    await init_db()
    try:
        await demo_service.seed_demo_workspace()
    except Exception:
        logger.exception("seed_demo_workspace failed at startup")
    try:
        yield
    finally:
        await close_db()


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


def _row_validation_handler(request: Request, exc: RowValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors})


app = FastAPI(
    title="Stash",
    description="Shared memory for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(RowValidationError, _row_validation_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
app.include_router(collab.router)
app.include_router(workspaces.router)
app.include_router(workspace_knowledge.router)
app.include_router(discover.router)
app.include_router(cartridge_invites.router)
app.include_router(cartridges.ws_router)
app.include_router(cartridges.public_router)
app.include_router(files_tree.router)
app.include_router(files_tree.canonical_router)
app.include_router(memory.ws_router)
app.include_router(tables.ws_router)
app.include_router(tables.router)
app.include_router(files.ws_router)
app.include_router(files.canonical_router)
app.include_router(batch.router)
app.include_router(transcripts.router)
app.include_router(aggregate.router)
app.include_router(skill.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(marketing.router)
app.include_router(sessions.router)
app.include_router(trash.router)
app.include_router(pins.router)
app.include_router(publish.router)
app.include_router(security_audit.router)
app.include_router(tasks.router)
app.include_router(integrations_router)
app.include_router(sources.router)
app.include_router(agent_chat.router)
app.include_router(session_folders.ws_router)
app.include_router(session_folders.public_router)
app.include_router(shares.router)
app.include_router(webhooks.router)
app.include_router(exports.router)
app.include_router(demo.router)

if settings.AUTH0_ENABLED:
    from backend.managed.auth0 import router as auth0_router

    app.include_router(auth0_router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Unhandled request failed method=%s exception_type=%s",
            request.method,
            type(exc).__name__,
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    for key, value in SECURITY_HEADERS.items():
        if key not in response.headers:
            response.headers[key] = value
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}
