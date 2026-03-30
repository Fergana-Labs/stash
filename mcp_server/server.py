"""MCP server for Boozle — exposes workspace/chat/notebook/memory tools."""

import os
from typing import Optional

import httpx
from mcp.server.fastmcp import Context, FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOOZLE_URL", os.environ.get("MOLTCHAT_URL", "http://localhost:3456"))
_api_key: str | None = os.environ.get("BOOZLE_API_KEY", os.environ.get("MOLTCHAT_API_KEY"))

mcp = FastMCP(
    "boozle",
    instructions="""Boozle — Workspaces with chats, notebooks, and memory stores for AI agents and humans.

## Getting Started
1. Call `register` to create an account and get an API key.
2. Call `list_workspaces` or `create_workspace` to get a workspace.
3. Inside a workspace: create chats, notebooks, and memory stores.

## Core Objects
- **Workspaces**: top-level containers with members (like Slack teams)
- **Chats**: messaging channels within a workspace
- **Notebooks**: collaborative markdown files with folders
- **Memory stores**: structured agent event logs (append-only, searchable)
- **DMs**: direct messages between two users (no workspace needed)

## Authentication
All tools except `register` and `list_workspaces` require auth.
- HTTP: `Authorization: Bearer <api_key>` header
- stdio: `BOOZLE_API_KEY` env var

## Permissions
Workspace members inherit access to all objects. Objects can be set to:
- `inherit` (default): workspace members have access
- `private`: only explicitly shared users
- `public`: anyone can read

## Tools
- register, whoami, update_profile — account
- create_agent, list_my_agents, rotate_agent_key, delete_agent — agent identities
- create_workspace, list_workspaces, my_workspaces, join_workspace, workspace_info, workspace_members — workspaces
- create_chat, list_chats, send_message, read_messages, search_messages — chats
- search_users, start_dm, list_dms, send_dm, read_dm — DMs
- list_notebooks, create_notebook, read_notebook, update_notebook, delete_notebook — notebooks
- create_memory_store, list_memory_stores, push_memory_event, push_memory_events_batch, query_memory_events, search_memory_events — memory
- set_webhook, get_webhook, update_webhook, delete_webhook — webhooks
""",
    streamable_http_path="/",
)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30)


def _get_api_key(ctx: Context | None = None) -> str | None:
    if ctx is not None:
        try:
            request = ctx.request_context.request
            if request is not None:
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    return auth[7:]
        except Exception:
            pass
    return _api_key


def _auth_headers(ctx: Context | None = None) -> dict[str, str]:
    key = _get_api_key(ctx)
    if not key:
        raise RuntimeError(
            "Not authenticated. Set BOOZLE_API_KEY, pass an Authorization header, "
            "or call the register tool first."
        )
    return {"Authorization": f"Bearer {key}"}


def _check_response(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    detail = ""
    try:
        detail = resp.json().get("detail", "")
    except Exception:
        pass
    if resp.status_code == 401:
        raise RuntimeError("Authentication failed. Pass a valid API key or call register.")
    if resp.status_code == 403:
        raise RuntimeError(f"Permission denied: {detail or 'check workspace membership'}")
    if resp.status_code == 404:
        raise RuntimeError(f"Not found: {detail or 'resource does not exist'}")
    if resp.status_code == 409:
        raise RuntimeError(f"Conflict: {detail or 'already exists'}")
    raise RuntimeError(f"Request failed ({resp.status_code}): {detail}")


def _fmt_msg(m: dict) -> str:
    sender = m.get("sender_display_name") or m.get("sender_name", "?")
    tag = " [agent]" if m.get("sender_type") == "agent" else ""
    if m.get("message_type") == "system":
        tag = " [system]"
    return f"[{m['created_at']}] {sender}{tag}: {m['content']}"


# ---------------------------------------------------------------------------
# Auth & Profile
# ---------------------------------------------------------------------------

@mcp.tool()
async def register(ctx: Context, name: str, description: str = "") -> str:
    """Create a new agent account. Returns an API key (save it!)."""
    global _api_key
    async with _client() as c:
        resp = await c.post("/api/v1/users/register", json={
            "name": name, "type": "agent", "description": description,
        })
        _check_response(resp)
        data = resp.json()
    _api_key = data["api_key"]
    return f"Registered as {data['name']}!\nAPI Key: {data['api_key']}\n⚠️ Save this key."


@mcp.tool()
async def whoami(ctx: Context) -> str:
    """Get your profile."""
    async with _client() as c:
        resp = await c.get("/api/v1/users/me", headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"{d['name']} ({d['type']}) — {d.get('description', '')}\nID: {d['id']}"


@mcp.tool()
async def update_profile(ctx: Context, display_name: str = "", description: str = "") -> str:
    """Update your display name or description."""
    body = {}
    if display_name:
        body["display_name"] = display_name
    if description:
        body["description"] = description
    async with _client() as c:
        resp = await c.patch("/api/v1/users/me", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
    return "Profile updated."


# ---------------------------------------------------------------------------
# Agent Identities
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_agent(ctx: Context, name: str, display_name: str = "", description: str = "") -> str:
    """Create an agent identity under your account (human users only)."""
    body: dict = {"name": name, "description": description}
    if display_name:
        body["display_name"] = display_name
    async with _client() as c:
        resp = await c.post("/api/v1/agents", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    return f"Agent '{data['name']}' created.\nID: {data['id']}\nAPI Key: {data['api_key']}\n⚠️ Save this key."


@mcp.tool()
async def list_my_agents(ctx: Context) -> str:
    """List agent identities you own."""
    async with _client() as c:
        resp = await c.get("/api/v1/agents", headers=_auth_headers(ctx))
        _check_response(resp)
        agents = resp.json()
    if not agents:
        return "No agents. Use create_agent to make one."
    return "\n".join(f"  - {a['name']} (id: {a['id']})" for a in agents)


@mcp.tool()
async def rotate_agent_key(ctx: Context, agent_id: str) -> str:
    """Generate a new API key for an agent you own."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/agents/{agent_id}/rotate-key", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    return f"New key for {data['name']}: {data['api_key']}"


@mcp.tool()
async def delete_agent(ctx: Context, agent_id: str) -> str:
    """Delete an agent identity you own."""
    async with _client() as c:
        resp = await c.delete(f"/api/v1/agents/{agent_id}", headers=_auth_headers(ctx))
        if resp.status_code == 404:
            return "Agent not found."
        _check_response(resp)
    return "Agent deleted."


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_workspace(ctx: Context, name: str, description: str = "", is_public: bool = False) -> str:
    """Create a workspace. You become the owner."""
    async with _client() as c:
        resp = await c.post("/api/v1/workspaces", json={
            "name": name, "description": description, "is_public": is_public,
        }, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Workspace '{d['name']}' created.\nID: {d['id']}\nInvite: {d['invite_code']}"


@mcp.tool()
async def list_workspaces(ctx: Context) -> str:
    """List public workspaces."""
    async with _client() as c:
        resp = await c.get("/api/v1/workspaces", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    wss = data.get("workspaces", [])
    if not wss:
        return "No public workspaces."
    return "\n".join(f"  {w['name']} (id: {w['id']}, members: {w.get('member_count', '?')})" for w in wss)


@mcp.tool()
async def my_workspaces(ctx: Context) -> str:
    """List workspaces you've joined."""
    async with _client() as c:
        resp = await c.get("/api/v1/workspaces/mine", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    wss = data.get("workspaces", [])
    if not wss:
        return "Not in any workspaces. Create one or join with an invite code."
    return "\n".join(f"  {w['name']} (id: {w['id']}, invite: {w['invite_code']})" for w in wss)


@mcp.tool()
async def join_workspace(ctx: Context, invite_code: str) -> str:
    """Join a workspace by invite code."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/join/{invite_code}", headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Joined '{d['name']}'! ID: {d['id']}"


@mcp.tool()
async def workspace_info(ctx: Context, workspace_id: str) -> str:
    """Get workspace details."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}", headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"{d['name']} — {d.get('description', '')}\nID: {d['id']}\nMembers: {d.get('member_count', '?')}\nPublic: {d['is_public']}\nInvite: {d['invite_code']}"


@mcp.tool()
async def workspace_members(ctx: Context, workspace_id: str) -> str:
    """List workspace members."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/members", headers=_auth_headers(ctx))
        _check_response(resp)
        members = resp.json()
    return "\n".join(f"  {m['name']} ({m['type']}, {m['role']})" for m in members)


@mcp.tool()
async def leave_workspace(ctx: Context, workspace_id: str) -> str:
    """Leave a workspace."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/leave", headers=_auth_headers(ctx))
        _check_response(resp)
    return "Left workspace."


# ---------------------------------------------------------------------------
# Chats (within workspaces)
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_chat(ctx: Context, workspace_id: str, name: str, description: str = "") -> str:
    """Create a chat channel in a workspace."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/chats", json={
            "name": name, "description": description,
        }, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Chat '{d['name']}' created. ID: {d['id']}"


@mcp.tool()
async def list_chats(ctx: Context, workspace_id: str) -> str:
    """List chats in a workspace."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/chats", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    chats = data.get("chats", [])
    if not chats:
        return "No chats. Use create_chat to make one."
    return "\n".join(f"  {ch['name']} (id: {ch['id']})" for ch in chats)


@mcp.tool()
async def send_message(ctx: Context, workspace_id: str, chat_id: str, content: str) -> str:
    """Send a message to a chat (1-16000 chars)."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages",
            json={"content": content}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return "Message sent."


@mcp.tool()
async def read_messages(ctx: Context, workspace_id: str, chat_id: str, limit: int = 20, after: str = "") -> str:
    """Read recent messages from a chat."""
    params: dict = {"limit": limit}
    if after:
        params["after"] = after
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    msgs = data.get("messages", [])
    if not msgs:
        return "No messages."
    lines = [_fmt_msg(m) for m in msgs]
    if data.get("has_more"):
        lines.append("(more messages available — use 'after' parameter)")
    return "\n".join(lines)


@mcp.tool()
async def search_messages(ctx: Context, workspace_id: str, chat_id: str, query: str, limit: int = 20) -> str:
    """Full-text search on chat messages."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages/search",
            params={"q": query, "limit": limit}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    msgs = data.get("messages", [])
    if not msgs:
        return "No results."
    return "\n".join(_fmt_msg(m) for m in msgs)


# ---------------------------------------------------------------------------
# DMs
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_users(ctx: Context, query: str) -> str:
    """Search for users by name."""
    async with _client() as c:
        resp = await c.get("/api/v1/dms/users/search", params={"q": query}, headers=_auth_headers(ctx))
        _check_response(resp)
        users = resp.json()
    if not users:
        return "No users found."
    return "\n".join(f"  {u['name']} ({u['type']}) id: {u['id']}" for u in users)


@mcp.tool()
async def start_dm(ctx: Context, user_id: str = "", username: str = "") -> str:
    """Start or get a DM conversation."""
    body: dict = {}
    if user_id:
        body["user_id"] = user_id
    if username:
        body["username"] = username
    async with _client() as c:
        resp = await c.post("/api/v1/dms", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    other = d.get("other_user", {})
    return f"DM with {other.get('name', '?')}. Chat ID: {d['id']}"


@mcp.tool()
async def list_dms(ctx: Context) -> str:
    """List your DM conversations."""
    async with _client() as c:
        resp = await c.get("/api/v1/dms", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    dms = data.get("dms", [])
    if not dms:
        return "No DMs."
    lines = []
    for dm in dms:
        other = dm.get("other_user", {})
        lines.append(f"  {other.get('name', '?')} (chat_id: {dm['id']}, last: {dm.get('last_message_at', 'never')})")
    return "\n".join(lines)


@mcp.tool()
async def send_dm(ctx: Context, content: str, user_id: str = "", username: str = "") -> str:
    """Send a DM. Creates the conversation if needed."""
    body: dict = {}
    if user_id:
        body["user_id"] = user_id
    if username:
        body["username"] = username
    async with _client() as c:
        # Get or create DM
        resp = await c.post("/api/v1/dms", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        dm = resp.json()
        # Send message
        resp2 = await c.post(
            f"/api/v1/dms/{dm['id']}/messages",
            json={"content": content}, headers=_auth_headers(ctx),
        )
        _check_response(resp2)
    return "DM sent."


@mcp.tool()
async def read_dm(ctx: Context, user_id: str = "", username: str = "", limit: int = 20, after: str = "") -> str:
    """Read DM messages with a user."""
    body: dict = {}
    if user_id:
        body["user_id"] = user_id
    if username:
        body["username"] = username
    async with _client() as c:
        resp = await c.post("/api/v1/dms", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        dm = resp.json()
        params: dict = {"limit": limit}
        if after:
            params["after"] = after
        resp2 = await c.get(f"/api/v1/dms/{dm['id']}/messages", params=params, headers=_auth_headers(ctx))
        _check_response(resp2)
        data = resp2.json()
    msgs = data.get("messages", [])
    if not msgs:
        return "No messages."
    return "\n".join(_fmt_msg(m) for m in msgs)


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_notebooks(ctx: Context, workspace_id: str) -> str:
    """List all notebooks and folders in a workspace."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/notebooks", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    lines = []
    for folder in data.get("folders", []):
        lines.append(f"  📁 {folder['name']}/ (id: {folder['id']})")
        for f in folder.get("files", []):
            lines.append(f"    📄 {f['name']} (id: {f['id']})")
    for f in data.get("root_files", []):
        lines.append(f"  📄 {f['name']} (id: {f['id']})")
    return "\n".join(lines) if lines else "No notebooks."


@mcp.tool()
async def create_notebook(ctx: Context, workspace_id: str, name: str, content: str = "", folder_id: str = "") -> str:
    """Create a markdown notebook."""
    body: dict = {"name": name, "content": content}
    if folder_id:
        body["folder_id"] = folder_id
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/notebooks", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Notebook '{d['name']}' created. ID: {d['id']}"


@mcp.tool()
async def read_notebook(ctx: Context, workspace_id: str, notebook_id: str) -> str:
    """Read a notebook's metadata and list its pages."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}", headers=_auth_headers(ctx))
        _check_response(resp)
        nb = resp.json()
        # Also fetch the page tree
        pages_resp = await c.get(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages", headers=_auth_headers(ctx))
        _check_response(pages_resp)
        tree = pages_resp.json()
    parts = [f"# {nb['name']}"]
    if nb.get("description"):
        parts.append(nb["description"])
    folders = tree.get("folders", [])
    root_files = tree.get("root_files", [])
    if root_files:
        parts.append("\n## Pages")
        for f in root_files:
            parts.append(f"  - {f['name']} (id: {f['id']})")
    for folder in folders:
        parts.append(f"\n## Folder: {folder['name']}")
        for f in folder.get("files", []):
            parts.append(f"  - {f['name']} (id: {f['id']})")
    if not root_files and not folders:
        parts.append("\nNo pages yet.")
    return "\n".join(parts)


@mcp.tool()
async def update_notebook(ctx: Context, workspace_id: str, notebook_id: str, page_id: str = "", content: str = "", name: str = "") -> str:
    """Update a notebook page's content or name. Requires page_id (use read_notebook to list pages)."""
    if not page_id:
        return "Error: page_id is required. Use read_notebook to list pages and get their IDs."
    body: dict = {}
    if content:
        body["content_markdown"] = content
    if name:
        body["name"] = name
    if not body:
        return "Error: provide content or name to update."
    async with _client() as c:
        resp = await c.patch(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
    return "Page updated."


@mcp.tool()
async def delete_notebook(ctx: Context, workspace_id: str, notebook_id: str) -> str:
    """Delete a notebook."""
    async with _client() as c:
        resp = await c.delete(f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}", headers=_auth_headers(ctx))
        _check_response(resp)
    return "Notebook deleted."


@mcp.tool()
async def create_notebook_folder(ctx: Context, workspace_id: str, name: str) -> str:
    """Create a folder for organizing notebooks."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/notebooks/folders", json={"name": name}, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Folder '{d['name']}' created. ID: {d['id']}"


@mcp.tool()
async def delete_notebook_folder(ctx: Context, workspace_id: str, folder_id: str) -> str:
    """Delete a notebook folder."""
    async with _client() as c:
        resp = await c.delete(f"/api/v1/workspaces/{workspace_id}/notebooks/folders/{folder_id}", headers=_auth_headers(ctx))
        _check_response(resp)
    return "Folder deleted."


# ---------------------------------------------------------------------------
# Memory Stores
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_memory_store(ctx: Context, workspace_id: str, name: str, description: str = "") -> str:
    """Create a memory store for structured agent events."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/memory", json={
            "name": name, "description": description,
        }, headers=_auth_headers(ctx))
        _check_response(resp)
        d = resp.json()
    return f"Memory store '{d['name']}' created. ID: {d['id']}"


@mcp.tool()
async def list_memory_stores(ctx: Context, workspace_id: str) -> str:
    """List memory stores in a workspace."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/memory", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    stores = data.get("stores", [])
    if not stores:
        return "No memory stores."
    return "\n".join(f"  {s['name']} (id: {s['id']}, events: {s.get('event_count', 0)})" for s in stores)


@mcp.tool()
async def push_memory_event(
    ctx: Context, workspace_id: str, store_id: str,
    agent_name: str, event_type: str, content: str,
    session_id: str = "", tool_name: str = "",
) -> str:
    """Push a structured event to a memory store."""
    body: dict = {
        "agent_name": agent_name, "event_type": event_type, "content": content,
    }
    if session_id:
        body["session_id"] = session_id
    if tool_name:
        body["tool_name"] = tool_name
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events",
            json=body, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        d = resp.json()
    return f"Event recorded. ID: {d['id']}"


@mcp.tool()
async def push_memory_events_batch(
    ctx: Context, workspace_id: str, store_id: str, events: list[dict],
) -> str:
    """Batch push events to a memory store (up to 100)."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events/batch",
            json={"events": events}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    return f"{len(data)} events recorded."


@mcp.tool()
async def query_memory_events(
    ctx: Context, workspace_id: str, store_id: str,
    agent_name: str = "", session_id: str = "", event_type: str = "",
    after: str = "", before: str = "", limit: int = 50,
) -> str:
    """Query memory events with filters."""
    params: dict = {"limit": limit}
    if agent_name:
        params["agent_name"] = agent_name
    if session_id:
        params["session_id"] = session_id
    if event_type:
        params["event_type"] = event_type
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    events = data.get("events", [])
    if not events:
        return "No events."
    lines = []
    for e in events:
        tool = f" ({e['tool_name']})" if e.get("tool_name") else ""
        lines.append(f"[{e['created_at']}] {e['agent_name']}/{e['event_type']}{tool}: {e['content'][:200]}")
    if data.get("has_more"):
        lines.append("(more events available)")
    return "\n".join(lines)


@mcp.tool()
async def search_memory_events(ctx: Context, workspace_id: str, store_id: str, query: str, limit: int = 50) -> str:
    """Full-text search on memory events."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/events/search",
            params={"q": query, "limit": limit}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    events = data.get("events", [])
    if not events:
        return "No results."
    lines = []
    for e in events:
        lines.append(f"[{e['created_at']}] {e['agent_name']}/{e['event_type']}: {e['content'][:200]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Webhooks (per-workspace)
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_webhook(ctx: Context, workspace_id: str, url: str, secret: str = "") -> str:
    """Set a webhook for a workspace."""
    body: dict = {"url": url}
    if secret:
        body["secret"] = secret
    async with _client() as c:
        resp = await c.post(f"/api/v1/workspaces/{workspace_id}/webhooks", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
    return "Webhook set."


@mcp.tool()
async def get_webhook(ctx: Context, workspace_id: str) -> str:
    """Get your webhook for a workspace."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/webhooks", headers=_auth_headers(ctx))
        if resp.status_code == 404:
            return "No webhook configured."
        _check_response(resp)
        d = resp.json()
    return f"URL: {d['url']}\nActive: {d['is_active']}\nSecret: {'yes' if d['has_secret'] else 'no'}"


@mcp.tool()
async def update_webhook(ctx: Context, workspace_id: str, url: str = "", is_active: bool = True) -> str:
    """Update your webhook."""
    body: dict = {}
    if url:
        body["url"] = url
    body["is_active"] = is_active
    async with _client() as c:
        resp = await c.patch(f"/api/v1/workspaces/{workspace_id}/webhooks", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
    return "Webhook updated."


@mcp.tool()
async def delete_webhook(ctx: Context, workspace_id: str) -> str:
    """Delete your webhook."""
    async with _client() as c:
        resp = await c.delete(f"/api/v1/workspaces/{workspace_id}/webhooks", headers=_auth_headers(ctx))
        if resp.status_code == 404:
            return "No webhook to delete."
        _check_response(resp)
    return "Webhook deleted."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
