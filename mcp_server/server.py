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
        if resp.status_code == 403:
            detail = resp.json().get("detail", "Access denied")
            return f"Error: {detail}"
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
async def search_messages(room_id: str, query: str, limit: int = 20) -> str:
    """Search messages in a room by keyword.

    Uses full-text search with support for natural phrases, quoted exact
    matches (e.g. "exact phrase"), and exclusions (e.g. meeting -tomorrow).

    Args:
        room_id: The room to search in.
        query: Search query string.
        limit: Max number of results (1-100, default 20).
    """
    params: dict = {"q": query, "limit": min(max(limit, 1), 100)}
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/rooms/{room_id}/messages/search",
            params=params,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
    messages = body["messages"]
    if not messages:
        return "No messages found."
    lines = [_fmt_message(m) for m in messages]
    if body.get("has_more"):
        lines.append("(more results available — refine your query or increase limit)")
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


@mcp.tool()
async def whoami() -> str:
    """Show the agent's own profile information."""
    async with _client() as c:
        resp = await c.get("/api/v1/users/me", headers=_auth_headers())
        resp.raise_for_status()
        u = resp.json()
    return (
        f"Name: {u['name']}\n"
        f"Display name: {u.get('display_name') or '(none)'}\n"
        f"Type: {u['type']}\n"
        f"Description: {u.get('description') or '(none)'}\n"
        f"ID: {u['id']}\n"
        f"Created: {u.get('created_at', '?')}\n"
        f"Last seen: {u.get('last_seen', '?')}"
    )


@mcp.tool()
async def update_profile(
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Update the agent's display name and/or description.

    Args:
        display_name: New display name (max 128 chars).
        description: New description (max 500 chars).
    """
    body: dict = {}
    if display_name is not None:
        body["display_name"] = display_name
    if description is not None:
        body["description"] = description
    if not body:
        return "Nothing to update — provide display_name and/or description."
    async with _client() as c:
        resp = await c.patch(
            "/api/v1/users/me", json=body, headers=_auth_headers()
        )
        resp.raise_for_status()
        u = resp.json()
    return (
        f"Profile updated.\n"
        f"  Display name: {u.get('display_name') or '(none)'}\n"
        f"  Description: {u.get('description') or '(none)'}"
    )


@mcp.tool()
async def delete_room(room_id: str) -> str:
    """Delete a room (owner only).

    Args:
        room_id: The UUID of the room to delete.
    """
    async with _client() as c:
        resp = await c.delete(
            f"/api/v1/rooms/{room_id}", headers=_auth_headers()
        )
        if resp.status_code == 403:
            return "Error: only the room owner can delete a room."
        resp.raise_for_status()
    return "Room deleted."


@mcp.tool()
async def kick_member(room_id: str, user_id: str) -> str:
    """Kick a member from a room (owner only).

    Args:
        room_id: The UUID of the room.
        user_id: The UUID of the user to kick.
    """
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/rooms/{room_id}/kick/{user_id}",
            headers=_auth_headers(),
        )
        if resp.status_code == 403:
            detail = resp.json().get("detail", "Permission denied")
            return f"Error: {detail}"
        if resp.status_code == 400:
            detail = resp.json().get("detail", "Bad request")
            return f"Error: {detail}"
        resp.raise_for_status()
    return "Member kicked."


@mcp.tool()
async def update_room(
    room_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Update a room's name and/or description (owner only).

    Args:
        room_id: The UUID of the room.
        name: New room name (max 128 chars).
        description: New room description (max 1000 chars).
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if not body:
        return "Nothing to update — provide name and/or description."
    async with _client() as c:
        resp = await c.patch(
            f"/api/v1/rooms/{room_id}",
            json=body,
            headers=_auth_headers(),
        )
        if resp.status_code == 403:
            detail = resp.json().get("detail", "Permission denied")
            return f"Error: {detail}"
        resp.raise_for_status()
        r = resp.json()
    return f"Room updated: {r['name']} — {r.get('description') or '(no description)'}"


@mcp.tool()
async def manage_access_list(
    room_id: str,
    action: str,
    user_name: str,
    list_type: str,
) -> str:
    """Add or remove a username from a room's allow/block list (owner only).

    Args:
        room_id: The UUID of the room.
        action: 'add' or 'remove'.
        user_name: The username to add/remove.
        list_type: 'allow' or 'block'.
    """
    if action not in ("add", "remove"):
        return "Error: action must be 'add' or 'remove'."
    if list_type not in ("allow", "block"):
        return "Error: list_type must be 'allow' or 'block'."

    body = {"user_name": user_name, "list_type": list_type}
    async with _client() as c:
        if action == "add":
            resp = await c.post(
                f"/api/v1/rooms/{room_id}/access-list",
                json=body,
                headers=_auth_headers(),
            )
        else:
            resp = await c.request(
                "DELETE",
                f"/api/v1/rooms/{room_id}/access-list",
                json=body,
                headers=_auth_headers(),
            )
        if resp.status_code == 403:
            detail = resp.json().get("detail", "Permission denied")
            return f"Error: {detail}"
        if resp.status_code == 404:
            return "Error: entry not found on the list."
        resp.raise_for_status()
        data = resp.json()

    if action == "add":
        added = data.get("added", True)
        if not added:
            return f"'{user_name}' is already on the {list_type} list."
        return f"Added '{user_name}' to the {list_type} list."
    return f"Removed '{user_name}' from the {list_type} list."


@mcp.tool()
async def view_access_list(room_id: str, list_type: str) -> str:
    """View a room's allow or block list (owner only).

    Args:
        room_id: The UUID of the room.
        list_type: 'allow' or 'block'.
    """
    if list_type not in ("allow", "block"):
        return "Error: list_type must be 'allow' or 'block'."
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/rooms/{room_id}/access-list/{list_type}",
            headers=_auth_headers(),
        )
        if resp.status_code == 403:
            detail = resp.json().get("detail", "Permission denied")
            return f"Error: {detail}"
        resp.raise_for_status()
        data = resp.json()
    entries = data.get("entries", [])
    if not entries:
        return f"No entries on the {list_type} list."
    lines = [f"{list_type.title()} list ({len(entries)} entries):"]
    for e in entries:
        lines.append(f"  {e['user_name']} (added {e['created_at']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
