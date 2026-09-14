"""What a bundled server's tool code needs from the host: the calling user,
and a FastMCP configured the way the mount serves it. Kept apart from the
mount so tool modules can import this without the mount importing them.
"""

from __future__ import annotations

from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

current_user_var: ContextVar[dict] = ContextVar("skill_server_current_user")


def current_user() -> dict:
    """The authenticated caller, for a tool body."""
    return current_user_var.get()


def new_server(name: str, instructions: str) -> FastMCP:
    """A FastMCP for this mount: stateless, JSON responses, rooted at the
    route itself, so every bundled server is served the same way."""
    return FastMCP(
        f"stash-{name}",
        instructions=instructions,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        # The mount's own bearer check runs first; the Host-header guard
        # would only reject the API's real hostname.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
