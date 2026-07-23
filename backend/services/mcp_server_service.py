"""Per-user MCP server registry.

Servers registered here surface in two places: the owner's own API/CLI
(`stash tools`, the Tools page) and the cloud agent — before each turn the
registry is materialized as a Claude-format `.mcp.json` in the sprite
workdir, so registered servers are available to the harness.

Secrets (http headers, stdio env) are encrypted at rest with the
integrations Fernet keyring — the same scheme as OAuth tokens.
"""

from __future__ import annotations

import json
import shlex
from uuid import UUID

from ..database import get_pool
from ..integrations.crypto import integration_fernet
from . import sprite_service


def _encrypt_json(values: dict[str, str]) -> bytes | None:
    if not values:
        return None
    return integration_fernet().encrypt(json.dumps(values).encode())


def _decrypt_json(ciphertext: bytes | None) -> dict[str, str]:
    if ciphertext is None:
        return {}
    return json.loads(integration_fernet().decrypt(bytes(ciphertext)).decode())


def _row_to_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "transport": row["transport"],
        "command": row["command"],
        "url": row["url"],
        "headers": _decrypt_json(row["headers_encrypted"]),
        "env": _decrypt_json(row["env_encrypted"]),
        "created_at": row["created_at"].isoformat(),
    }


async def list_servers(owner_user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, name, transport, command, url, headers_encrypted, env_encrypted, created_at "
        "FROM mcp_servers WHERE owner_user_id = $1 ORDER BY name",
        owner_user_id,
    )
    return [_row_to_dict(r) for r in rows]


async def create_server(
    owner_user_id: UUID,
    name: str,
    transport: str,
    command: str | None,
    url: str | None,
    headers: dict[str, str],
    env: dict[str, str],
) -> dict:
    """Insert one server. Raises asyncpg.UniqueViolationError on a duplicate
    name — the router maps that to 409."""
    row = await get_pool().fetchrow(
        """
        INSERT INTO mcp_servers
            (owner_user_id, name, transport, command, url, headers_encrypted, env_encrypted)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, name, transport, command, url, headers_encrypted, env_encrypted, created_at
        """,
        owner_user_id,
        name,
        transport,
        command,
        url,
        _encrypt_json(headers),
        _encrypt_json(env),
    )
    return _row_to_dict(row)


async def delete_server(owner_user_id: UUID, server_id: UUID) -> bool:
    """True if a row was deleted; False when it doesn't exist in this scope."""
    status = await get_pool().execute(
        "DELETE FROM mcp_servers WHERE id = $1 AND owner_user_id = $2",
        server_id,
        owner_user_id,
    )
    return status == "DELETE 1"


def claude_entry(server: dict) -> dict:
    """One server as a Claude Code `.mcp.json` mcpServers entry."""
    if server["transport"] == "stdio":
        parts = shlex.split(server["command"])
        entry: dict = {"type": "stdio", "command": parts[0], "args": parts[1:]}
        if server["env"]:
            entry["env"] = server["env"]
        return entry
    entry = {"type": "http", "url": server["url"]}
    if server["headers"]:
        entry["headers"] = server["headers"]
    return entry


async def sync_sprite_config(user_id: UUID, sprite: sprite_service.Sprite) -> None:
    """Write the user's registry as `.mcp.json` in the sprite workdir.

    Written every turn (like the OAuth credential files) so removals
    propagate too — the file always mirrors the registry exactly.
    """
    servers = await list_servers(user_id)
    config = {"mcpServers": {s["name"]: claude_entry(s) for s in servers}}
    await sprite_service.write_file(
        sprite,
        f"{sprite_service.SPRITE_WORKDIR}/.mcp.json",
        json.dumps(config, indent=2) + "\n",
    )
