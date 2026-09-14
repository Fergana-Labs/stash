"""Serving a bundled MCP server behind bearer auth at /mcp/<name>.

Auth is the ordinary Stash API key. The user is resolved once per request
and handed to the tools through a context variable, so every tool is scoped
to the caller's own account without the server knowing how it was reached.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth import authenticate_token
from .registry import SERVERS
from .tools import current_user_var

_built: dict[str, FastMCP] = {}


class _BearerAuth:
    """Resolve the bearer key before the MCP app sees the request. Read-only
    keys are refused outright: tools act, they do not merely read."""

    def __init__(self, app: ASGIApp, name: str):
        self.app = app
        # The rate-limit middleware names every route's endpoint the way it
        # would a function; an ASGI object without these is a 500.
        self.__name__ = f"mcp_{name}"
        self.__qualname__ = self.__name__

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # The server is addressed by the route path itself (/mcp/<name>), but
        # the inner router only knows "/": present the request as its root.
        base = scope["path"].rstrip("/")
        scope = {**scope, "root_path": base, "path": base + "/"}
        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        if not header.lower().startswith("bearer "):
            await JSONResponse({"detail": "Missing Authorization header"}, 401)(
                scope, receive, send
            )
            return
        try:
            user = await authenticate_token(header[7:].strip())
        except HTTPException as error:
            await JSONResponse({"detail": error.detail}, error.status_code)(scope, receive, send)
            return
        if user["key_access"] != "full":
            await JSONResponse({"detail": "This API key is read-only"}, 403)(scope, receive, send)
            return
        token = current_user_var.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_var.reset(token)


def mount_all(app: FastAPI) -> None:
    # A route, not a mount: a mount would redirect the bare /mcp/<name> to a
    # trailing slash, and that is the URL skills declare.
    for name, build in SERVERS.items():
        server = build()
        _built[name] = server
        app.add_route(
            f"/mcp/{name}",
            _BearerAuth(server.streamable_http_app(), name),
            methods=["GET", "POST", "DELETE"],
        )


@contextlib.asynccontextmanager
async def lifespan() -> AsyncIterator[None]:
    """The streamable-HTTP transport needs its session manager running for
    the life of the process, and FastAPI does not run a mounted app's
    lifespan. It runs in its own task so entering and leaving happen in one
    place whatever task the caller is on."""
    started = asyncio.Event()
    stop = asyncio.Event()

    async def keep_running() -> None:
        async with contextlib.AsyncExitStack() as stack:
            for server in _built.values():
                await stack.enter_async_context(server.session_manager.run())
            started.set()
            await stop.wait()

    runner = asyncio.create_task(keep_running())
    await started.wait()
    try:
        yield
    finally:
        stop.set()
        await runner
