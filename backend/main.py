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
    aggregate,
    collab,
    discover,
    exports,
    files,
    files_tree,
    imports,
    memory,
    publish,
    sessions,
    skill,
    stash_invites,
    stashes,
    tables,
    tasks,
    transcripts,
    trash,
    users,
    workspace_knowledge,
    workspaces,
)
from .services.row_validation import RowValidationError

logger = logging.getLogger("stash")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background workers (file extraction, embedding reconcile, viz
    # precompute, session summarizer) now run in the Celery `worker` and
    # `beat` services — see backend/celery_app.py.
    await init_db()
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
app.include_router(stash_invites.router)
app.include_router(stashes.ws_router)
app.include_router(stashes.public_router)
app.include_router(files_tree.router)
app.include_router(memory.ws_router)
app.include_router(tables.ws_router)
app.include_router(files.ws_router)
app.include_router(transcripts.router)
app.include_router(aggregate.router)
app.include_router(skill.router)
app.include_router(admin.router)
app.include_router(sessions.router)
app.include_router(trash.router)
app.include_router(publish.router)
app.include_router(tasks.router)
app.include_router(integrations_router)
app.include_router(imports.router)
app.include_router(exports.router)

if settings.AUTH0_ENABLED:
    from backend.managed.auth0 import router as auth0_router

    app.include_router(auth0_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
