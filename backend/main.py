import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from .config import settings
from .database import close_db, init_db
from .middleware import limiter
from .routers import (
    aggregate,
    files,
    memory,
    notebooks,
    skill,
    tables,
    transcripts,
    users,
    workspaces,
)
from .services.row_validation import RowValidationError
from .workers import dispatcher as extraction_dispatcher
from .workers import embedding_reconciler, viz_precompute

logger = logging.getLogger("stash")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    dispatcher_task = asyncio.create_task(extraction_dispatcher.run())
    reconciler_task = asyncio.create_task(embedding_reconciler.run())
    viz_task = asyncio.create_task(viz_precompute.run())
    try:
        yield
    finally:
        for task in (dispatcher_task, reconciler_task, viz_task):
            task.cancel()
        for task in (dispatcher_task, reconciler_task, viz_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
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
app.include_router(workspaces.router)
app.include_router(notebooks.ws_router)
app.include_router(notebooks.ws_pages_router)
app.include_router(memory.ws_router)
app.include_router(tables.ws_router)
app.include_router(files.ws_router)
app.include_router(transcripts.router)
app.include_router(aggregate.router)
app.include_router(skill.router)

if settings.AUTH0_ENABLED:
    from backend.managed.auth0 import router as auth0_router

    app.include_router(auth0_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
