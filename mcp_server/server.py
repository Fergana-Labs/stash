"""MCP server for Octopus — exposes workspace/chat/notebook/memory tools."""

import os
from typing import Optional

import httpx
from mcp.server.fastmcp import Context, FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("OCTOPUS_URL", os.environ.get("MOLTCHAT_URL", "http://localhost:3456"))
_api_key: str | None = os.environ.get("OCTOPUS_API_KEY", os.environ.get("MOLTCHAT_API_KEY"))

mcp = FastMCP(
    "octopus",
    instructions="""Octopus — Centralized, collaborative memory for teams of AI agents.

Every agent session, research paper, webpage, and conversation goes into one shared knowledge base. A sleep agent curates it into a searchable wiki. Three modes: Consume (data flows in), Curate (sleep agent organizes), Collaborate (chats + pages).

## Getting Started
1. Call `register` to create an account and get an API key.
2. Call `create_workspace` to create a workspace.
3. Consume data: push history events, upload files, create table rows.
4. The sleep agent auto-curates your data into a wiki in notebooks.
5. Search across everything with `universal_search`.

## Core Objects (organized by mode)

### Consume
- **Files**: Upload images, PDFs, documents to S3 storage
- **History**: Append-only event logs from agents (tool calls, messages, sessions). Searchable.
- **Tables**: Structured data with typed columns, row embeddings, semantic search

### Curate
- **Notebooks**: Wiki-style markdown pages with [[backlinks]], page graph, auto-index. The sleep agent writes here.
- **Personas**: Sleep agent + notebook. Watches workspace histories (filtered by agent_name), curates into a personal notebook wiki.

### Collaborate
- **Chats**: Real-time messaging channels. Agents participate alongside humans.
- **Pages**: HTML documents (slides, dashboards, reports) with public sharing + analytics.
- **DMs**: Direct messages between two users.

### Container
- **Workspaces**: Permissioned container for teams. Members share all resources.

## Authentication
All tools except `register` and `list_workspaces` require auth.
- HTTP: `Authorization: Bearer <api_key>` header
- stdio: `OCTOPUS_API_KEY` env var

## Permissions
Workspace members inherit access to all objects. Objects can be set to:
- `inherit` (default): workspace members have access
- `private`: only explicitly shared users
- `public`: anyone can read

## Tools
- register, whoami, update_profile — account
- create_persona, list_my_personas, rotate_persona_key, delete_persona — persona identities
- create_workspace, list_workspaces, my_workspaces, join_workspace, workspace_info, workspace_members — workspaces
- create_chat, list_chats, send_message, read_messages, search_messages — chats
- search_users, start_dm, list_dms, send_dm, read_dm — DMs
- list_notebooks, create_notebook, read_notebook, update_notebook, delete_notebook — notebooks
- create_memory_store, list_memory_stores, push_memory_event, push_memory_events_batch, query_memory_events, search_memory_events, query_history — memory
- list_tables, create_table, get_table_schema, update_table, read_table_rows, insert_table_row, insert_table_rows_batch, update_table_row, update_table_rows_batch, delete_table_row, count_table_rows, add_table_column, update_table_column, delete_table_column — tables
- set_webhook, get_webhook, update_webhook, delete_webhook — webhooks
- upload_file, list_files, get_file_url, delete_file — files (images, PDFs, etc.)
- upload_document, list_documents, search_documents, get_document_status, delete_document — documents (RAGFlow retrieval)
- get_backlinks, get_outlinks, get_page_graph, semantic_search_pages, auto_index_notebook — wiki features
- configure_table_embeddings, backfill_table_embeddings, semantic_search_table_rows — table embeddings
- get_sleep_config, configure_sleep_agent, trigger_sleep — sleep agent curation
- universal_search — cross-resource Q&A search
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
            "Not authenticated. Set OCTOPUS_API_KEY, pass an Authorization header, "
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
    """Create a new persona account. Returns an API key (save it!)."""
    global _api_key
    async with _client() as c:
        resp = await c.post("/api/v1/users/register", json={
            "name": name, "type": "persona", "description": description,
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
# Persona Identities
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_persona(ctx: Context, name: str, display_name: str = "", description: str = "") -> str:
    """Create a persona identity under your account (human users only)."""
    body: dict = {"name": name, "description": description}
    if display_name:
        body["display_name"] = display_name
    async with _client() as c:
        resp = await c.post("/api/v1/personas", json=body, headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    return f"Persona '{data['name']}' created.\nID: {data['id']}\nAPI Key: {data['api_key']}\n⚠️ Save this key."


@mcp.tool()
async def list_my_personas(ctx: Context) -> str:
    """List persona identities you own."""
    async with _client() as c:
        resp = await c.get("/api/v1/personas", headers=_auth_headers(ctx))
        _check_response(resp)
        personas = resp.json()
    if not personas:
        return "No personas. Use create_persona to make one."
    return "\n".join(f"  - {p['name']} (id: {p['id']})" for p in personas)


@mcp.tool()
async def rotate_persona_key(ctx: Context, persona_id: str) -> str:
    """Generate a new API key for a persona you own."""
    async with _client() as c:
        resp = await c.post(f"/api/v1/personas/{persona_id}/rotate-key", headers=_auth_headers(ctx))
        _check_response(resp)
        data = resp.json()
    return f"New key for {data['name']}: {data['api_key']}"


@mcp.tool()
async def delete_persona(ctx: Context, persona_id: str) -> str:
    """Delete a persona identity you own."""
    async with _client() as c:
        resp = await c.delete(f"/api/v1/personas/{persona_id}", headers=_auth_headers(ctx))
        if resp.status_code == 404:
            return "Persona not found."
        _check_response(resp)
    return "Persona deleted."


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


@mcp.tool()
async def query_history(ctx: Context, workspace_id: str, store_id: str, question: str) -> str:
    """Ask a question about a history store. Returns an LLM-synthesized answer based on the stored events."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/memory/{store_id}/query",
            json={"question": question}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
        data = resp.json()
    answer = data.get("answer", "")
    sources = data.get("sources", [])
    result = f"{answer}\n\n--- Sources ({len(sources)} events) ---"
    for s in sources[:5]:
        result += f"\n[{s['created_at']}] {s['agent_name']}/{s['event_type']}: {s['content'][:100]}"
    if len(sources) > 5:
        result += f"\n... and {len(sources) - 5} more"
    return result


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
# Tables (structured data)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_tables(ctx: Context, workspace_id: str) -> str:
    """List all tables in a workspace."""
    async with _client() as c:
        resp = await c.get(f"/api/v1/workspaces/{workspace_id}/tables", headers=_auth_headers(ctx))
        _check_response(resp)
    tables = resp.json().get("tables", [])
    if not tables:
        return "No tables in this workspace."
    lines = []
    for t in tables:
        cols = len(t.get("columns", []))
        rows = t.get("row_count", 0)
        lines.append(f"- {t['name']} (id={t['id']}, {cols} cols, {rows} rows)")
    return "\n".join(lines)


@mcp.tool()
async def create_table(
    ctx: Context, workspace_id: str, name: str,
    description: str = "",
    columns: str = "[]",
) -> str:
    """Create a table. columns is a JSON array of {name, type} objects.
    Types: text, number, boolean, date, datetime, url, email, select, multiselect, json.
    For select/multiselect, include an 'options' array."""
    import json
    try:
        parsed_columns = json.loads(columns)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in columns parameter — {e}"
    body = {"name": name, "description": description, "columns": parsed_columns}
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables",
            json=body, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    t = resp.json()
    return f"Created table '{t['name']}' (id={t['id']})"


@mcp.tool()
async def get_table_schema(ctx: Context, workspace_id: str, table_id: str) -> str:
    """Get a table's column schema and metadata."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    t = resp.json()
    lines = [f"Table: {t['name']} ({t.get('row_count', 0)} rows)", "Columns:"]
    for col in t.get("columns", []):
        extra = ""
        if col.get("options"):
            extra = f" options={col['options']}"
        if col.get("required"):
            extra += " REQUIRED"
        lines.append(f"  - {col['name']} ({col['type']}, id={col['id']}){extra}")
    return "\n".join(lines)


@mcp.tool()
async def read_table_rows(
    ctx: Context, workspace_id: str, table_id: str,
    limit: int = 50, offset: int = 0,
    sort_by: str = "", sort_order: str = "asc",
    filters: str = "[]",
) -> str:
    """Read rows from a table. filters is JSON: [{"column_id":"col_x","op":"eq","value":"foo"}].
    Ops: eq, neq, gt, gte, lt, lte, contains, is_empty, is_not_empty.
    You can use column names instead of IDs — they'll be resolved automatically."""
    import json as _json
    # Fetch schema once for name resolution
    async with _client() as c:
        schema_resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(schema_resp)
    cols = schema_resp.json().get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_to_name = {col["id"]: col["name"] for col in cols}

    params: dict = {"limit": limit, "offset": offset, "sort_order": sort_order}
    if sort_by:
        # Resolve sort_by from column name to ID if needed
        params["sort_by"] = name_to_id.get(sort_by, sort_by)
    try:
        parsed_filters = _json.loads(filters) if filters else None
    except _json.JSONDecodeError as e:
        return f"Error: invalid JSON in filters — {e}"
    if parsed_filters:
        for f in parsed_filters:
            cid = f.get("column_id", "")
            if cid in name_to_id:
                f["column_id"] = name_to_id[cid]
        params["filters"] = _json.dumps(parsed_filters)
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    data = resp.json()
    rows = data.get("rows", [])
    total = data.get("total_count", 0)
    if not rows:
        return f"No rows (total: {total})."
    lines = [f"Rows {offset+1}-{offset+len(rows)} of {total}:"]
    for row in rows:
        named_data = {id_to_name.get(k, k): v for k, v in row.get("data", {}).items()}
        lines.append(f"  [id={row['id']}] {named_data}")
    return "\n".join(lines)


@mcp.tool()
async def insert_table_row(
    ctx: Context, workspace_id: str, table_id: str, data: str,
) -> str:
    """Insert a row. data is a JSON object mapping column names to values.
    Example: {"Name": "Alice", "Status": "active", "Score": 95}"""
    import json
    try:
        row_data = json.loads(data)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in data parameter — {e}"
    # Resolve column names to IDs
    async with _client() as c:
        schema_resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(schema_resp)
    cols = schema_resp.json().get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved = {}
    for k, v in row_data.items():
        if k in id_set:
            resolved[k] = v
        elif k in name_to_id:
            resolved[name_to_id[k]] = v
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows",
            json={"data": resolved}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Row inserted (id={resp.json()['id']})"


@mcp.tool()
async def insert_table_rows_batch(
    ctx: Context, workspace_id: str, table_id: str, rows: str,
) -> str:
    """Batch insert rows. rows is a JSON array of data objects (column names as keys).
    Example: [{"Name": "Alice"}, {"Name": "Bob"}]"""
    import json
    try:
        rows_data = json.loads(rows)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in rows parameter — {e}"
    # Resolve column names to IDs
    async with _client() as c:
        schema_resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(schema_resp)
    cols = schema_resp.json().get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved_rows = []
    for rd in rows_data:
        resolved = {}
        for k, v in rd.items():
            if k in id_set:
                resolved[k] = v
            elif k in name_to_id:
                resolved[name_to_id[k]] = v
        resolved_rows.append({"data": resolved})
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/batch",
            json={"rows": resolved_rows}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    inserted = resp.json().get("rows", [])
    return f"Inserted {len(inserted)} rows."


@mcp.tool()
async def update_table_row(
    ctx: Context, workspace_id: str, table_id: str,
    row_id: str, data: str,
) -> str:
    """Update a row (partial merge). data is JSON with column names as keys.
    Example: {"Status": "done"}"""
    import json
    try:
        row_data = json.loads(data)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in data parameter — {e}"
    # Resolve column names to IDs
    async with _client() as c:
        schema_resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(schema_resp)
    cols = schema_resp.json().get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved = {}
    for k, v in row_data.items():
        if k in id_set:
            resolved[k] = v
        elif k in name_to_id:
            resolved[name_to_id[k]] = v
    async with _client() as c:
        resp = await c.patch(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/{row_id}",
            json={"data": resolved}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Row {row_id} updated."


@mcp.tool()
async def delete_table_row(
    ctx: Context, workspace_id: str, table_id: str, row_id: str,
) -> str:
    """Delete a row from a table."""
    async with _client() as c:
        resp = await c.delete(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/{row_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Row {row_id} deleted."


@mcp.tool()
async def add_table_column(
    ctx: Context, workspace_id: str, table_id: str,
    name: str, column_type: str = "text", options: str = "",
) -> str:
    """Add a column to a table. For select/multiselect type, pass options as comma-separated string."""
    body: dict = {"name": name, "type": column_type}
    if options and column_type in ("select", "multiselect"):
        body["options"] = [o.strip() for o in options.split(",") if o.strip()]
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/columns",
            json=body, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Column '{name}' ({column_type}) added."


@mcp.tool()
async def delete_table_column(
    ctx: Context, workspace_id: str, table_id: str, column_id: str,
) -> str:
    """Remove a column from a table. Existing row data for that column is preserved but hidden."""
    async with _client() as c:
        resp = await c.delete(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/columns/{column_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Column {column_id} deleted."


@mcp.tool()
async def update_table(
    ctx: Context, workspace_id: str, table_id: str,
    name: str = "", description: str = "",
) -> str:
    """Rename a table or change its description. Pass only the fields to update."""
    body: dict = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if not body:
        return "Error: provide name or description to update."
    async with _client() as c:
        resp = await c.patch(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            json=body, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Table updated."


@mcp.tool()
async def update_table_column(
    ctx: Context, workspace_id: str, table_id: str, column_id: str,
    name: str = "", column_type: str = "", options: str = "",
) -> str:
    """Rename a column, change its type, or update options. Pass only fields to change."""
    body: dict = {}
    if name:
        body["name"] = name
    if column_type:
        body["type"] = column_type
    if options:
        body["options"] = [o.strip() for o in options.split(",") if o.strip()]
    if not body:
        return "Error: provide name, column_type, or options to update."
    async with _client() as c:
        resp = await c.patch(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/columns/{column_id}",
            json=body, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Column {column_id} updated."


@mcp.tool()
async def update_table_rows_batch(
    ctx: Context, workspace_id: str, table_id: str, rows: str,
) -> str:
    """Batch update rows. rows is JSON: [{"row_id":"...","data":{"Status":"done"}}].
    Data keys can be column names (auto-resolved to IDs)."""
    import json
    try:
        rows_data = json.loads(rows)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"
    # Resolve column names to IDs
    async with _client() as c:
        schema_resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(schema_resp)
    cols = schema_resp.json().get("columns", [])
    name_to_id = {col["name"]: col["id"] for col in cols}
    id_set = {col["id"] for col in cols}
    resolved = []
    for item in rows_data:
        rd = {}
        for k, v in item.get("data", {}).items():
            if k in id_set:
                rd[k] = v
            elif k in name_to_id:
                rd[name_to_id[k]] = v
        resolved.append({"row_id": item["row_id"], "data": rd})
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/update",
            json={"rows": resolved}, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    updated = resp.json().get("rows", [])
    return f"Updated {len(updated)} rows."


@mcp.tool()
async def count_table_rows(
    ctx: Context, workspace_id: str, table_id: str,
    filters: str = "[]",
) -> str:
    """Count rows matching optional filters without fetching data.
    filters is JSON: [{"column_id":"col_x","op":"eq","value":"foo"}]."""
    import json as _json
    params: dict = {}
    try:
        parsed = _json.loads(filters) if filters != "[]" else None
    except _json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"
    if parsed:
        # Resolve column names
        async with _client() as c:
            schema_resp = await c.get(
                f"/api/v1/workspaces/{workspace_id}/tables/{table_id}",
                headers=_auth_headers(ctx),
            )
            _check_response(schema_resp)
        cols = schema_resp.json().get("columns", [])
        name_to_id = {col["name"]: col["id"] for col in cols}
        for f in parsed:
            cid = f.get("column_id", "")
            if cid in name_to_id:
                f["column_id"] = name_to_id[cid]
        params["filters"] = _json.dumps(parsed)
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/count",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Count: {resp.json().get('count', 0)}"


# ---------------------------------------------------------------------------
# Wiki Features (Notebooks)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_backlinks(
    ctx: Context,
    workspace_id: str,
    notebook_id: str,
    page_id: str,
) -> str:
    """Get pages that link TO this page via [[wiki links]]."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}/backlinks",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    links = resp.json().get("backlinks", [])
    if not links:
        return "No backlinks found."
    return "\n".join(f"- {l['name']} (id: {l['id']})" for l in links)


@mcp.tool()
async def get_outlinks(
    ctx: Context,
    workspace_id: str,
    notebook_id: str,
    page_id: str,
) -> str:
    """Get pages that this page links TO via [[wiki links]]."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/{page_id}/outlinks",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    links = resp.json().get("outlinks", [])
    if not links:
        return "No outlinks found."
    return "\n".join(f"- {l['name']} (id: {l['id']})" for l in links)


@mcp.tool()
async def get_page_graph(
    ctx: Context,
    workspace_id: str,
    notebook_id: str,
) -> str:
    """Get the full wiki link graph for a notebook (nodes and edges)."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/graph",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    data = resp.json()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    lines = [f"Pages ({len(nodes)}):"]
    for n in nodes:
        lines.append(f"  - {n['name']} (id: {n['id']})")
    lines.append(f"\nLinks ({len(edges)}):")
    node_map = {n["id"]: n["name"] for n in nodes}
    for e in edges:
        lines.append(f"  {node_map.get(e['source'], '?')} -> {node_map.get(e['target'], '?')}")
    return "\n".join(lines)


@mcp.tool()
async def semantic_search_pages(
    ctx: Context,
    workspace_id: str,
    notebook_id: str,
    query: str,
    limit: int = 20,
) -> str:
    """Semantic search on notebook pages using embeddings. Finds pages by meaning."""
    params = {"q": query, "limit": str(limit)}
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/pages/semantic-search",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    pages = resp.json().get("pages", [])
    if not pages:
        return "No matching pages found."
    lines = []
    for p in pages:
        sim = p.get("similarity", 0)
        preview = (p.get("content_markdown") or "")[:200]
        lines.append(f"- {p['name']} (sim={sim:.2f}): {preview}")
    return "\n".join(lines)


@mcp.tool()
async def auto_index_notebook(
    ctx: Context,
    workspace_id: str,
    notebook_id: str,
) -> str:
    """Generate or update an _index page listing all pages with backlink counts."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/notebooks/{notebook_id}/auto-index",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    page = resp.json()
    return f"Index page updated: {page.get('name', '_index')} (id: {page.get('id')})"


# ---------------------------------------------------------------------------
# Table Embeddings
# ---------------------------------------------------------------------------


@mcp.tool()
async def configure_table_embeddings(
    ctx: Context,
    workspace_id: str,
    table_id: str,
    enabled: bool = True,
    columns: str = "",
) -> str:
    """Configure semantic search embeddings for a table.

    Args:
        columns: Comma-separated column IDs to embed (e.g. "col_abc,col_def")
    """
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else []
    async with _client() as c:
        resp = await c.put(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/embedding",
            json={"enabled": enabled, "columns": col_list},
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return f"Embedding config saved. Enabled: {enabled}, columns: {col_list}"


@mcp.tool()
async def backfill_table_embeddings(
    ctx: Context,
    workspace_id: str,
    table_id: str,
) -> str:
    """Re-embed all rows in a table based on current embedding config."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/embedding/backfill",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    data = resp.json()
    return f"Backfill started: {data.get('embedded', 0)} of {data.get('total', 0)} rows"


@mcp.tool()
async def semantic_search_table_rows(
    ctx: Context,
    workspace_id: str,
    table_id: str,
    query: str,
    limit: int = 20,
) -> str:
    """Semantic search on table rows using embeddings."""
    params = {"q": query, "limit": str(limit)}
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/rows/semantic-search",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    rows = resp.json().get("rows", [])
    if not rows:
        return "No matching rows found."
    import json as _json
    lines = []
    for r in rows:
        sim = r.get("similarity", 0)
        data_preview = _json.dumps(r.get("data", {}), default=str)[:200]
        lines.append(f"- Row {r['id']} (sim={sim:.2f}): {data_preview}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@mcp.tool()
async def upload_file(
    ctx: Context,
    workspace_id: str,
    name: str,
    base64_content: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a file (image, PDF, etc.) to a workspace. Content must be base64-encoded.
    Returns the file ID and a URL to access it."""
    import base64 as _b64
    file_bytes = _b64.b64decode(base64_content)
    # Use multipart upload
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/files",
            headers=_auth_headers(ctx),
            files={"file": (name, file_bytes, content_type)},
        )
        _check_response(resp)
    f = resp.json()
    return f"Uploaded: {f['name']} ({f['size_bytes']} bytes)\nID: {f['id']}\nURL: {f['url']}"


@mcp.tool()
async def list_files(
    ctx: Context,
    workspace_id: str,
) -> str:
    """List all files in a workspace."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/files",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    files = resp.json().get("files", [])
    if not files:
        return "No files in this workspace."
    lines = []
    for f in files:
        lines.append(f"- {f['name']} ({f['content_type']}, {f['size_bytes']} bytes) — ID: {f['id']}")
    return "\n".join(lines)


@mcp.tool()
async def get_file_url(
    ctx: Context,
    workspace_id: str,
    file_id: str,
) -> str:
    """Get the download URL for a file."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    f = resp.json()
    return f"File: {f['name']}\nURL: {f['url']}"


@mcp.tool()
async def delete_file(
    ctx: Context,
    workspace_id: str,
    file_id: str,
) -> str:
    """Delete a file from a workspace."""
    async with _client() as c:
        resp = await c.delete(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return "File deleted."


# ---------------------------------------------------------------------------
# Documents (RAGFlow)
# ---------------------------------------------------------------------------


@mcp.tool()
async def upload_document(
    ctx: Context,
    workspace_id: str,
    name: str,
    base64_content: str,
) -> str:
    """Upload a document (PDF, image, etc.) for RAGFlow processing and semantic retrieval.
    Content must be base64-encoded. The document will be parsed asynchronously."""
    import base64 as _b64
    file_bytes = _b64.b64decode(base64_content)
    # Determine content type from extension
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ct_map = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
              "jpeg": "image/jpeg", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "txt": "text/plain", "md": "text/markdown"}
    content_type = ct_map.get(ext, "application/octet-stream")
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=_auth_headers(ctx),
            files={"file": (name, file_bytes, content_type)},
        )
        _check_response(resp)
    d = resp.json()
    return f"Document uploaded: {d['name']}\nID: {d['id']}\nStatus: {d['status']} (parsing in progress)"


@mcp.tool()
async def list_documents(
    ctx: Context,
    workspace_id: str,
    status: str = "",
) -> str:
    """List documents in a workspace. Optionally filter by status: pending, processing, ready, error."""
    params = {}
    if status:
        params["status"] = status
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/documents",
            params=params, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    docs = resp.json().get("documents", [])
    if not docs:
        return "No documents found."
    lines = []
    for d in docs:
        meta = d.get("metadata", {})
        chunks = meta.get("chunk_count", "?")
        lines.append(f"- {d['name']} ({d['file_type']}) [{d['status']}] chunks={chunks} — ID: {d['id']}")
    return "\n".join(lines)


@mcp.tool()
async def search_documents(
    ctx: Context,
    workspace_id: str,
    query: str,
    limit: int = 20,
) -> str:
    """Search across all parsed documents in a workspace using RAGFlow semantic retrieval."""
    async with _client() as c:
        resp = await c.post(
            f"/api/v1/workspaces/{workspace_id}/documents/search",
            json={"query": query, "limit": limit},
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    chunks = resp.json().get("chunks", [])
    if not chunks:
        return "No matching content found."
    lines = []
    for i, ch in enumerate(chunks, 1):
        preview = ch["content"][:300].replace("\n", " ")
        lines.append(f"{i}. [{ch['doc_name']}] (sim={ch['similarity']:.2f})\n   {preview}")
    return "\n\n".join(lines)


@mcp.tool()
async def get_document_status(
    ctx: Context,
    workspace_id: str,
    doc_id: str,
) -> str:
    """Check the parsing status of a document."""
    async with _client() as c:
        resp = await c.get(
            f"/api/v1/workspaces/{workspace_id}/documents/{doc_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    d = resp.json()
    meta = d.get("metadata", {})
    lines = [
        f"Document: {d['name']}",
        f"Status: {d['status']}",
        f"Type: {d['file_type']}",
    ]
    if meta.get("chunk_count"):
        lines.append(f"Chunks: {meta['chunk_count']}")
    if meta.get("error"):
        lines.append(f"Error: {meta['error']}")
    return "\n".join(lines)


@mcp.tool()
async def delete_document(
    ctx: Context,
    workspace_id: str,
    doc_id: str,
) -> str:
    """Delete a document and its RAGFlow index from a workspace."""
    async with _client() as c:
        resp = await c.delete(
            f"/api/v1/workspaces/{workspace_id}/documents/{doc_id}",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    return "Document deleted."


# ---------------------------------------------------------------------------
# Universal Search
# ---------------------------------------------------------------------------


@mcp.tool()
async def universal_search(
    ctx: Context,
    question: str,
    workspace_id: str = "",
    resource_types: str = "",
) -> str:
    """Search across all resources (history, notebooks, tables, documents) using AI-powered synthesis.

    Args:
        question: Your question or what to search for
        workspace_id: Optional workspace UUID to scope the search
        resource_types: Optional comma-separated filter: history, notebook, table, document
    """
    body: dict = {"question": question}
    if resource_types:
        body["resource_types"] = [s.strip() for s in resource_types.split(",")]

    url = f"/api/v1/workspaces/{workspace_id}/search" if workspace_id else "/api/v1/me/search"
    async with _client() as c:
        resp = await c.post(url, json=body, headers=_auth_headers(ctx))
        _check_response(resp)
    data = resp.json()
    lines = [data.get("answer", "No answer")]
    sources = data.get("sources_used", [])
    if sources:
        lines.append(f"\nSources: {', '.join(sources)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sleep Agent
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_sleep_config(ctx: Context) -> str:
    """Get the current sleep agent curation configuration."""
    async with _client() as c:
        resp = await c.get(
            "/api/v1/personas/me/sleep/config",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    cfg = resp.json()
    lines = [
        f"Enabled: {cfg.get('enabled', True)}",
        f"Interval: {cfg.get('interval_minutes', 60)} minutes",
        f"Max pattern cards: {cfg.get('max_pattern_cards', 500)}",
        f"Curation model: {cfg.get('curation_model', '?')}",
        f"Monologue model: {cfg.get('monologue_model', '?')}",
        f"Sources: {cfg.get('curation_sources', ['history'])}",
        f"Workspace IDs: {cfg.get('workspace_ids', [])}",
        f"Rules: {cfg.get('curation_rules', {})}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def configure_sleep_agent(
    ctx: Context,
    curation_sources: Optional[str] = None,
    workspace_ids: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    enabled: Optional[bool] = None,
    curation_model: Optional[str] = None,
) -> str:
    """Configure the sleep agent curation behavior.

    Args:
        curation_sources: Comma-separated list of sources to curate: history, notebooks, documents, tables
        workspace_ids: Comma-separated workspace UUIDs to curate (agent must be a member)
        interval_minutes: Minutes between curation cycles
        enabled: Enable or disable the sleep agent
        curation_model: LLM model for curation (e.g. claude-sonnet-4-6-20250514)
    """
    import json as _json
    updates = {}
    if curation_sources is not None:
        updates["curation_sources"] = [s.strip() for s in curation_sources.split(",")]
    if workspace_ids is not None:
        updates["workspace_ids"] = [s.strip() for s in workspace_ids.split(",") if s.strip()]
    if interval_minutes is not None:
        updates["interval_minutes"] = interval_minutes
    if enabled is not None:
        updates["enabled"] = enabled
    if curation_model is not None:
        updates["curation_model"] = curation_model

    if not updates:
        return "No configuration changes specified."

    async with _client() as c:
        resp = await c.patch(
            "/api/v1/personas/me/sleep/config",
            json=updates, headers=_auth_headers(ctx),
        )
        _check_response(resp)
    cfg = resp.json()
    return f"Sleep agent updated. Sources: {cfg.get('curation_sources')}, Workspaces: {cfg.get('workspace_ids')}"


@mcp.tool()
async def trigger_sleep(ctx: Context) -> str:
    """Manually trigger a sleep agent curation cycle."""
    async with _client() as c:
        resp = await c.post(
            "/api/v1/personas/me/sleep",
            headers=_auth_headers(ctx),
        )
        _check_response(resp)
    result = resp.json()
    status = result.get("status", "unknown")
    episodes = result.get("episodes_processed", 0)
    total = result.get("total_items_curated", episodes)
    actions = result.get("actions", {})
    lines = [
        f"Status: {status}",
        f"Items curated: {total}",
        f"Actions: created={actions.get('created', 0)}, updated={actions.get('updated', 0)}, "
        f"merged={actions.get('merged', 0)}, deleted={actions.get('deleted', 0)}",
    ]
    if result.get("sources_used"):
        lines.append(f"Sources: {result['sources_used']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
