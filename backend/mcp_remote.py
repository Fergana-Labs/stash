"""Remote MCP endpoint — the same tools the `stash-mcp` CLI serves, reachable
over HTTPS instead of only from the machine they're installed on.

Why this exists: `cli/mcp_server.py` runs on the user's laptop and reads their
API key out of `~/.stash/config.json`. That works for Claude Code, and cannot
work for anything running elsewhere — Cowork's cloud sessions, Claude on the
web, Claude on a phone. Those reach tools only over HTTP with OAuth.

Two things are worth understanding before editing this file.

**Tools call our own REST API, in process.** Every tool here is a thin wrapper
over a route that already exists, invoked through an in-process ASGI transport
carrying the caller's own bearer token. No network hop, and — the point —
authorization, scoping, plan gates, and rate limits are enforced by exactly the
same code that enforces them for the web app. Re-implementing 72 tools against
the service layer would mean a second authorization path to keep correct, and
the first missed scope check is a data leak between users.

**The audience is this endpoint's own URL.** Claude sends the MCP server URL as
the OAuth `resource` parameter; with Auth0's resource-parameter compatibility
profile enabled, that lands in the token's `aud`. So MCP tokens and web-app
tokens are separate credentials and neither is accepted where the other is
expected. Requires those tenant toggles to be on — without them Auth0 ignores
`resource` and every call here 401s.
"""

import logging
from urllib.parse import urlparse

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from .config import settings

logger = logging.getLogger(__name__)

# Set by attach(); the FastAPI app tools call back into. A module global rather
# than an import because main.py imports this module, not the other way round.
_asgi_app: Starlette | None = None


class Auth0TokenVerifier(TokenVerifier):
    """Verifies Auth0 access tokens minted for this endpoint's audience."""

    async def verify_token(self, token: str) -> AccessToken | None:
        from .managed.auth0.jwt import validate_auth0_token_for_audience

        try:
            claims = await validate_auth0_token_for_audience(token, settings.MCP_PUBLIC_URL)
        except Exception:
            # The library's contract is None for "not a valid token", while the
            # validator raises HTTPException. Expired and malformed tokens are
            # routine here — Claude refreshes reactively on a 401.
            return None

        subject = claims.get("sub")
        if not subject:
            return None
        return AccessToken(
            token=token,
            client_id=claims.get("azp") or subject,
            scopes=(claims.get("scope") or "").split(),
            expires_at=claims.get("exp"),
            resource=settings.MCP_PUBLIC_URL,
            subject=subject,
            claims=claims,
        )


def _caller_token(ctx: Context) -> str:
    """The bearer token of whoever is making this MCP call."""
    from mcp.server.auth.middleware.auth_context import get_access_token

    access = get_access_token()
    if access is None:
        # Unreachable while auth is configured: the transport rejects
        # unauthenticated requests before a tool runs. Loud rather than a call
        # that silently acts as nobody.
        raise RuntimeError("MCP tool ran without an authenticated caller")
    return access.token


async def _api_get(ctx: Context, path: str, **params) -> dict:
    return await _api_request(ctx, "GET", path, params=params)


async def _api_post(ctx: Context, path: str, json: dict) -> dict:
    return await _api_request(ctx, "POST", path, json=json)


async def _api_request(ctx: Context, method: str, path: str, **kwargs) -> dict:
    """Call our own REST API in-process as the authenticated caller."""
    if _asgi_app is None:
        raise RuntimeError("Remote MCP endpoint used before attach()")
    transport = httpx.ASGITransport(app=_asgi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://stash.internal", timeout=60
    ) as client:
        resp = await client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {_caller_token(ctx)}"},
            **kwargs,
        )
    # Surface the API's own error text: an MCP tool that swallows a 403 and
    # returns an empty result teaches the model the data does not exist.
    resp.raise_for_status()
    return resp.json()


def _build_server() -> FastMCP:
    """Construct the MCP server. Only ever called from attach(), and only once
    it has confirmed the endpoint is configured — so a server object cannot
    exist in an unauthenticated state waiting for someone to mount it."""
    server = FastMCP(
        "stash",
        instructions="Stash — your team's shared memory. Search everything you "
        "and your agents have written, read it, and write back into it.",
        token_verifier=Auth0TokenVerifier(),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(f"https://{settings.AUTH0_DOMAIN}/"),
            resource_server_url=AnyHttpUrl(settings.MCP_PUBLIC_URL),
            required_scopes=[],
        ),
        # The app is mounted at the URL's own path, so its internal route sits
        # at the mount root. Left at the default "/mcp" it would answer at
        # /mcp/mcp and the advertised URL would 404.
        streamable_http_path="/",
    )
    for tool in (stash_search, stash_vfs, stash_list_workspaces):
        server.tool()(tool)
    return server


async def stash_search(
    ctx: Context,
    query: str,
    limit: int = 20,
) -> dict:
    """Search across everything in the user's Stash — their own files and
    pages, their agents' session transcripts, and every connected source
    (GitHub, Drive, Gmail, Notion, Slack, Granola) — merged onto one relevance
    scale. Returns {"results": [...], "has_more": bool}."""
    return await _api_get(ctx, "/api/v1/me/sources/search", q=query, limit=limit)


async def stash_vfs(ctx: Context, script: str, cwd: str = "/") -> dict:
    """Browse the Stash as a filesystem with bash-shaped commands over the
    virtual tree: `ls /`, `find / -maxdepth 3 -type f`, `rg 'query' /`,
    `cat '/files/README.md'`. Mounts are /files /sessions /memory /skills
    /tables /sources."""
    return await _api_post(ctx, "/api/v1/me/vfs", {"script": script, "cwd": cwd})


async def stash_list_workspaces(ctx: Context) -> dict:
    """List the workspaces this user belongs to, and which one is active."""
    return await _api_get(ctx, "/api/v1/me/workspaces")


def attach(app) -> bool:
    """Mount the remote MCP endpoint onto the FastAPI app.

    Returns whether it mounted. It needs both an Auth0 tenant to verify tokens
    against and the canonical public URL that is its own OAuth audience, so a
    deployment without those (self-hosted, local dev, CI) simply doesn't serve
    it — announced in the log rather than half-mounted.
    """
    global _asgi_app

    if not settings.MCP_PUBLIC_URL or not settings.AUTH0_DOMAIN:
        logger.info(
            "remote MCP endpoint not mounted (needs MCP_PUBLIC_URL and AUTH0_DOMAIN)",
        )
        return False

    _asgi_app = app
    # Mounted at MCP_PUBLIC_URL's own path, so the URL the user types into
    # Claude is the URL that answers — Claude requires the advertised `resource`
    # to match the connector URL exactly, path included.
    path = urlparse(settings.MCP_PUBLIC_URL).path.rstrip("/")
    if not path:
        raise RuntimeError(
            f"MCP_PUBLIC_URL needs a path to mount at (got {settings.MCP_PUBLIC_URL!r}); "
            "use something like https://api.joinstash.ai/mcp"
        )
    # Claude discovers the authorization server by probing
    # /.well-known/oauth-protected-resource/<path> at the *origin*, so these
    # routes go on the main app — inside the mount they'd only be reachable at
    # a path Claude never asks for.
    for route in create_protected_resource_routes(
        resource_url=AnyHttpUrl(settings.MCP_PUBLIC_URL),
        authorization_servers=[AnyHttpUrl(f"https://{settings.AUTH0_DOMAIN}/")],
        resource_name="Stash",
    ):
        app.router.routes.append(route)

    app.mount(path, _build_server().streamable_http_app())
    logger.info("remote MCP endpoint mounted at %s", settings.MCP_PUBLIC_URL)
    return True
