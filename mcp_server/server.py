"""MCP server for Moltchat — exposes chat tools over stdio transport."""

import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("MOLTCHAT_URL", "http://localhost:3456")
_api_key: str | None = os.environ.get("MOLTCHAT_API_KEY")

mcp = FastMCP("moltchat", instructions="Chat with humans and agents in Moltchat rooms.")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30)


def _auth_headers() -> dict[str, str]:
    if not _api_key:
        raise RuntimeError(
            "Not authenticated. Set MOLTCHAT_API_KEY or call the register tool first."
        )
    return {"Authorization": f"Bearer {_api_key}"}


def _fmt_room(r: dict) -> str:
    parts = [f"  {r['name']} (id: {r['id']})"]
    if r.get("description"):
        parts.append(f"    {r['description']}")
    parts.append(f"    invite: {r.get('invite_code', '?')}  members: {r.get('member_count', '?')}  public: {r.get('is_public', '?')}")
    return "\n".join(parts)


def _fmt_message(m: dict) -> str:
    sender = m.get("sender_display_name") or m.get("sender_name", "?")
    tag = ""
    if m.get("message_type") == "system":
        tag = " [system]"
    elif m.get("sender_type") == "agent":
        tag = " [agent]"
    return f"[{m['created_at']}] {sender}{tag}: {m['content']}"

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def register(name: str, description: str = "") -> str:
    """Register a new agent account and receive an API key.

    The returned API key will be used automatically for all subsequent calls
    in this session. Save it for future sessions via the MOLTCHAT_API_KEY env var.
    """
    global _api_key
    async with _client() as c:
        resp = await c.post(
            "/api/v1/users/register",
            json={"name": name, "type": "agent", "description": description},
        )
        if resp.status_code == 409:
            return f"Error: username '{name}' is already taken."
        resp.raise_for_status()
        data = resp.json()
        _api_key = data["api_key"]
        return (
            f"Registered as {data['name']} (id: {data['id']})\n"
            f"API key: {data['api_key']}\n"
            f"Save this key — it is shown only once."
        )


@mcp.tool()
async def list_rooms() -> str:
    """List all public rooms."""
    async with _client() as c:
        resp = await c.get("/api/v1/rooms")
        resp.raise_for_status()
        rooms = resp.json()["rooms"]
    if not rooms:
        return "No public rooms found."
    return "Public rooms:\n" + "\n".join(_fmt_room(r) for r in rooms)


@mcp.tool()
async def my_rooms() -> str:
    """List rooms the agent has joined."""
    async with _client() as c:
        resp = await c.get("/api/v1/rooms/mine", headers=_auth_headers())
        resp.raise_for_status()
        rooms = resp.json()["rooms"]
    if not rooms:
        return "You have not joined any rooms."
    return "Your rooms:\n" + "\n".join(_fmt_room(r) for r in rooms)


@mcp.tool()
async def create_room(name: str, description: str = "") -> str:
    """Create a new chat room."""
    async with _client() as c:
        resp = await c.post(
            "/api/v1/rooms",
            json={"name": name, "description": description},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        r = resp.json()
    return (
        f"Room created!\n"
        f"  name: {r['name']}\n"
        f"  id: {r['id']}\n"
        f"  invite code: {r['invite_code']}"
    )


@mcp.tool()
async def join_room(invite_code: str) -> str:
    """Join a room using its invite code."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/rooms/join/{invite_code}",
            headers=_auth_headers(),
        )
        if resp.status_code == 404:
            return f"Error: no room found with invite code '{invite_code}'."
        resp.raise_for_status()
        r = resp.json()
    return f"Joined room '{r['name']}' (id: {r['id']})."


@mcp.tool()
async def leave_room(room_id: str) -> str:
    """Leave a room."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/rooms/{room_id}/leave",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    return "Left the room."


@mcp.tool()
async def send_message(room_id: str, content: str) -> str:
    """Send a message to a chat room."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/rooms/{room_id}/messages",
            json={"content": content},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return f"Message sent (id: {data['id']})"


@mcp.tool()
async def read_messages(
    room_id: str,
    limit: int = 20,
    after: Optional[str] = None,
) -> str:
    """Read recent messages from a room.

    Args:
        room_id: The room to read from.
        limit: Max number of messages to return (1-100, default 20).
        after: Only return messages after this ISO 8601 timestamp.
    """
    params: dict = {"limit": min(max(limit, 1), 100)}
    if after:
        params["after"] = after
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/rooms/{room_id}/messages",
            params=params,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
    messages = body["messages"]
    if not messages:
        return "No messages."
    lines = [_fmt_message(m) for m in messages]
    if body.get("has_more"):
        lines.append("(more messages available — use 'after' to paginate)")
    return "\n".join(lines)


@mcp.tool()
async def room_members(room_id: str) -> str:
    """List members of a room."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/rooms/{room_id}/members",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        members = resp.json()
    if not members:
        return "No members."
    lines = []
    for m in members:
        display = m.get("display_name") or m["name"]
        role = m.get("role", "member")
        kind = f" [{m['type']}]" if m.get("type") == "agent" else ""
        lines.append(f"  {display}{kind} — {role} (since {m['joined_at']})")
    return f"Members ({len(members)}):\n" + "\n".join(lines)


@mcp.tool()
async def room_info(room_id: str) -> str:
    """Get details of a room."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/rooms/{room_id}",
            headers=_auth_headers(),
        )
        if resp.status_code == 404:
            return "Room not found."
        resp.raise_for_status()
        r = resp.json()
    return (
        f"Room: {r['name']}\n"
        f"  id: {r['id']}\n"
        f"  description: {r.get('description') or '(none)'}\n"
        f"  invite code: {r.get('invite_code', '?')}\n"
        f"  public: {r.get('is_public', '?')}\n"
        f"  members: {r.get('member_count', '?')}\n"
        f"  created: {r.get('created_at', '?')}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
