"""Per-user MCP server registry, plus the servers installed skills declare.

Servers registered here surface in two places: the owner's own API/CLI
(`stash tools`, the Tools page) and the cloud agent — before each turn the
registry is materialized as a Claude-format `.mcp.json` in the sprite
workdir, so registered servers are available to the harness.

A skill can also bring a tool server: one `mcp: <name> <url>` line in its
SKILL.md frontmatter. Nothing is registered for it; the config writer reads
the user's installed skills each turn and adds what they declare, so adding
the skill is what makes the tools appear and removing it makes them go.

Secrets (http headers, stdio env) are encrypted at rest with the
integrations Fernet keyring — the same scheme as OAuth tokens.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from urllib.parse import urlparse
from uuid import UUID

from ..config import settings
from ..database import get_pool
from ..integrations.crypto import integration_fernet
from . import skill_service, sprite_service

logger = logging.getLogger(__name__)

_DECLARATION_RE = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9_-]{0,99})\s+(https?://\S+)$")

# The harness expands this from the turn's environment, so the key never
# lands in a file. `sprite_service.agent_env` supplies it.
_SKILL_SERVER_AUTH = "Bearer ${STASH_API_KEY}"


def _own_api_origin() -> str:
    """Where the harness reaches this API from: the sprite's configured URL,
    or this machine in local exec mode (mirrors `sprite_service.agent_env`)."""
    if settings.AGENT_EXEC_MODE == "local":
        return f"http://localhost:{settings.PORT}"
    return settings.SPRITES_STASH_API_URL


def _same_origin(url: str, base: str) -> bool:
    a, b = urlparse(url), urlparse(base)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


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


def parse_declaration(value: str) -> tuple[str, str] | None:
    """`"<name> <url>"` from a SKILL.md `mcp:` line, or None when it is not
    one. An empty value is the common case (most skills bring no server);
    anything else that fails to parse is a broken skill, not a server."""
    match = _DECLARATION_RE.match(value.strip())
    if match is None:
        return None
    return match.group(1), match.group(2)


async def skill_declared_entries(user_id: UUID) -> dict[str, dict]:
    """`.mcp.json` entries for every server the user's installed skills
    declare, keyed by server name."""
    entries: dict[str, dict] = {}
    for skill in await skill_service.list_skills(user_id, user_id):
        if not skill["mcp"]:
            continue
        parsed = parse_declaration(skill["mcp"])
        if parsed is None:
            logger.warning(
                "skill %r declares an unparseable mcp server: %r", skill["name"], skill["mcp"]
            )
            continue
        name, url = parsed
        entry: dict = {"type": "http", "url": url}
        # The user's key goes only to our own API. Anyone can publish a
        # skill, so a declared server on any other host is just a server —
        # it never receives the credential.
        if _same_origin(url, _own_api_origin()):
            entry["headers"] = {"Authorization": _SKILL_SERVER_AUTH}
        entries[name] = entry
    return entries


async def sprite_config(user_id: UUID) -> dict:
    """What `.mcp.json` holds: the registry plus skill-declared servers. A
    registry row wins a name collision — it is the user's own explicit
    configuration — and the loss is logged rather than hidden."""
    entries = await skill_declared_entries(user_id)
    for server in await list_servers(user_id):
        if server["name"] in entries:
            logger.warning("registered MCP server %r shadows a skill-declared one", server["name"])
        entries[server["name"]] = claude_entry(server)
    return {"mcpServers": entries}


async def sync_sprite_config(user_id: UUID, sprite: sprite_service.Sprite) -> None:
    """Write `.mcp.json` in the sprite workdir.

    Written every turn (like the OAuth credential files) so removals
    propagate too — the file always mirrors the registry and the installed
    skills exactly.
    """
    config = await sprite_config(user_id)
    await sprite_service.write_workdir_file(
        sprite, ".mcp.json", json.dumps(config, indent=2) + "\n"
    )
