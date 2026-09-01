"""One hosted MCP server per kind, at /mcp/<kind>.

This is how a skill brings its tools: its SKILL.md names this URL, the
config writers put it in front of the harness, and the harness's own MCP
client does the rest. Nothing runs on the user's machine and nothing is
added to the plugin's tool list — an agent without the skill never sees
these tools.

Auth is the ordinary bearer API key. The user is resolved once per request
and handed to the tools through a context variable, so every tool is scoped
to the caller's own account.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth import authenticate_token
from . import registry, service

_current_user: ContextVar[dict] = ContextVar("trained_models_current_user")

_servers: dict[str, FastMCP] = {}


def _user() -> dict:
    return _current_user.get()


class _BearerAuth:
    """Resolve the bearer key before the MCP app sees the request. Read-only
    keys are refused outright: every tool here spends or produces."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # The server is addressed by the route path itself (/mcp/<kind>), but
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
        token = _current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user.reset(token)


def _generic_tools(mcp: FastMCP, kind: str) -> None:
    @mcp.tool()
    async def setup_status() -> dict:
        """Call this first. Which models exist and their state, whether a paid
        training run is waiting to be used, and the next step to take."""
        user = _user()
        return await service.setup_status(user["id"], user, kind)

    @mcp.tool()
    async def check_corpus(folder: str) -> dict:
        """Judge a folder of the user's writing before training. Free and
        instant. Reports usable words, what was ignored, duplicates, and any
        blocker. `folder` is a folder name or id in the user's Files."""
        user = _user()
        try:
            report, folder_row = await service.check_corpus(user["id"], user["id"], kind, folder)
        except (service.FolderNotFound, service.AmbiguousFolder) as error:
            return {"status": "error", "message": str(error)}
        return {
            "folder": {"id": str(folder_row["id"]), "name": folder_row["name"]},
            **report.to_dict(),
        }

    @mcp.tool()
    async def train(name: str, folder: str) -> dict:
        """Start a training run on a folder of the user's writing. Returns the
        queued model, or `payment_required` with a checkout link the user must
        open and pay (one-time fee per run) — relay the link, wait for them to
        say they've paid, then call train again with the same arguments.
        Poll job_result until the model is ready; about six minutes."""
        user = _user()
        try:
            model = await service.train(user["id"], user, kind, name, folder)
        except service.PaymentRequired as error:
            return {
                "status": "payment_required",
                "fee": f"${error.amount_cents // 100} one-time, then unlimited use",
                "checkout_url": error.checkout_url,
                "hint": "Give the user this link. Once they've paid, call train again.",
            }
        except service.CorpusNotReady as error:
            return {"status": "corpus_not_ready", **error.report.to_dict()}
        except (
            service.FolderNotFound,
            service.AmbiguousFolder,
            service.NameTaken,
            service.BadName,
        ) as error:
            return {"status": "error", "message": str(error)}
        return {"status": model["status"], "model": service.public(model)}

    @mcp.tool()
    async def job_result(model: str, job_id: str | None = None) -> dict:
        """Progress of a training run (omit job_id) or of a generation that
        came back pending (pass its job_id)."""
        user = _user()
        try:
            if job_id is None:
                return {"model": service.public(await service.get_model(user["id"], kind, model))}
            return await service.job_result(user["id"], kind, model, job_id)
        except service.ModelNotFound as error:
            return {"status": "error", "message": str(error)}

    @mcp.tool()
    async def list_models() -> list[dict]:
        """Every model of this kind the user has, with status."""
        return [service.public(m) for m in await service.list_models(_user()["id"], kind)]

    @mcp.tool()
    async def delete_model(name: str) -> dict:
        """Delete a model. Only on the user's explicit say-so; it cannot be
        undone and a new one costs a training run."""
        deleted = await service.delete_model(_user()["id"], kind, name)
        return {"deleted": deleted}


def _run_for(kind: str) -> Callable[[str, str, dict], Awaitable[dict]]:
    async def run_op(model: str, op: str, payload: dict) -> dict:
        user = _user()
        try:
            return await service.run(user["id"], kind, model, op, payload)
        except (service.ModelNotFound, service.ModelNotReady, ValueError) as error:
            return {"status": "error", "message": str(error)}

    return run_op


def build(kind: str) -> ASGIApp:
    module = registry.get(kind)
    mcp = FastMCP(
        f"stash-{kind}",
        instructions=f"{module.TITLE}: models trained on the user's own material. "
        "Call setup_status first.",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        # Our own bearer check runs first; the Host-header guard would only
        # reject the API's real hostname.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    _generic_tools(mcp, kind)
    module.register_tools(mcp, _run_for(kind))
    _servers[kind] = mcp
    return _BearerAuth(mcp.streamable_http_app())


def mount_all(app: FastAPI) -> None:
    # A route, not a mount: a mount would redirect the bare /mcp/<kind> to a
    # trailing slash, and that is the URL skills declare.
    for kind in registry.KINDS:
        app.add_route(f"/mcp/{kind}", build(kind), methods=["GET", "POST", "DELETE"])


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
            for mcp in _servers.values():
                await stack.enter_async_context(mcp.session_manager.run())
            started.set()
            await stop.wait()

    runner = asyncio.create_task(keep_running())
    await started.wait()
    try:
        yield
    finally:
        stop.set()
        await runner
