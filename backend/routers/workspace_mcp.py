"""Workspace MCP proxy: upstream server registry + the proxied MCP endpoint.

POST /api/v1/workspaces/{id}/mcp is a stateless streamable-HTTP MCP server.
Agents connect with their existing Stash API key:

    claude mcp add --transport http stash-mcp \\
        https://api.joinstash.ai/api/v1/workspaces/<id>/mcp \\
        --header "Authorization: Bearer <stash api key>"
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import mcp_proxy_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["mcp"])


class McpServerCreateRequest(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = {}
    tool_allowlist: list[str] = []


class McpServerUpdateRequest(BaseModel):
    url: str | None = None
    headers: dict[str, str] | None = None
    tool_allowlist: list[str] | None = None


async def _require_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@router.get("/{workspace_id}/mcp-servers")
async def list_mcp_servers(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    return {"servers": await mcp_proxy_service.list_servers(workspace_id)}


@router.post("/{workspace_id}/mcp-servers", status_code=201)
async def register_mcp_server(
    workspace_id: UUID,
    req: McpServerCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    try:
        return await mcp_proxy_service.create_server(
            workspace_id, req.name, req.url, req.headers, req.tool_allowlist
        )
    except mcp_proxy_service.McpProxyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{workspace_id}/mcp-servers/{name}")
async def update_mcp_server(
    workspace_id: UUID,
    name: str,
    req: McpServerUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    server = await mcp_proxy_service.update_server(
        workspace_id, name, url=req.url, headers=req.headers, tool_allowlist=req.tool_allowlist
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


@router.delete("/{workspace_id}/mcp-servers/{name}", status_code=204)
async def delete_mcp_server(
    workspace_id: UUID,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    if not await mcp_proxy_service.delete_server(workspace_id, name):
        raise HTTPException(status_code=404, detail="MCP server not found")


@router.get("/{workspace_id}/mcp-servers/{name}/tools")
async def list_mcp_server_tools(
    workspace_id: UUID,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Live tool listing from the upstream, for curating the allowlist."""
    await _require_member(workspace_id, current_user["id"])
    try:
        tools = await mcp_proxy_service.list_upstream_tools(workspace_id, name)
    except mcp_proxy_service.McpProxyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream MCP server unreachable: {e}")
    return {"tools": tools}


@router.post("/{workspace_id}/mcp")
async def mcp_endpoint(
    workspace_id: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    message = await request.json()
    response = await mcp_proxy_service.handle_rpc(workspace_id, message)
    if response is None:
        return Response(status_code=202)
    return JSONResponse(response)


@router.get("/{workspace_id}/mcp")
async def mcp_endpoint_get(workspace_id: UUID):
    # Streamable HTTP clients may GET to open a server-push SSE stream; this
    # proxy is stateless and never pushes, which a 405 signals per the spec.
    raise HTTPException(status_code=405, detail="server-initiated streams not supported")
