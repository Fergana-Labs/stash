"""Per-user MCP server registry: the API behind the Tools page and
`stash tools`. Strictly private to the owner — no sharing surface."""

from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..auth import get_current_user
from ..services import mcp_server_service

router = APIRouter(prefix="/api/v1/me", tags=["mcp-servers"])


class McpServerCreate(BaseModel):
    # The name becomes the mcpServers key in Claude Code config files.
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    transport: Literal["stdio", "http"]
    command: str | None = None
    url: str | None = None
    headers: dict[str, str] = {}
    env: dict[str, str] = {}

    @model_validator(mode="after")
    def check_transport_fields(self) -> "McpServerCreate":
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio transport requires command")
            if self.url or self.headers:
                raise ValueError("stdio transport takes command/env, not url/headers")
        else:
            if not self.url:
                raise ValueError("http transport requires url")
            if not self.url.startswith(("http://", "https://")):
                raise ValueError("url must start with http:// or https://")
            if self.command or self.env:
                raise ValueError("http transport takes url/headers, not command/env")
        return self


@router.get("/mcp-servers")
async def list_mcp_servers(current_user: dict = Depends(get_current_user)) -> list[dict]:
    return await mcp_server_service.list_servers(current_user["id"])


@router.post("/mcp-servers", status_code=201)
async def create_mcp_server(
    req: McpServerCreate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return await mcp_server_service.create_server(
            current_user["id"],
            req.name,
            req.transport,
            req.command,
            req.url,
            req.headers,
            req.env,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"MCP server '{req.name}' already exists")


@router.delete("/mcp-servers/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> None:
    deleted = await mcp_server_service.delete_server(current_user["id"], server_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")
