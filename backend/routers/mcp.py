"""The Stash MCP proxy endpoint.

A stateless streamable-HTTP MCP server exposing the read-only tools of the
user's connected integrations (see services/mcp_proxy_service.py). Agents
connect with their existing Stash API key:

    claude mcp add --transport http stash https://api.joinstash.ai/api/v1/mcp \\
        --header "Authorization: Bearer <stash api key>"

Connecting/disconnecting providers happens through the regular integrations
flow (/api/v1/integrations) — this router only serves the protocol.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..auth import get_current_user
from ..services import mcp_proxy_service

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.post("")
async def mcp_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    message = await request.json()
    response = await mcp_proxy_service.handle_rpc(current_user["id"], message)
    if response is None:
        return Response(status_code=202)
    return JSONResponse(response)


@router.get("")
async def mcp_endpoint_get():
    # Streamable HTTP clients may GET to open a server-push SSE stream; this
    # proxy is stateless and never pushes, which a 405 signals per the spec.
    raise HTTPException(status_code=405, detail="server-initiated streams not supported")
