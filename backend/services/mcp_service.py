"""MCP server exposing Stash to any MCP client over SSE.

Architecture
------------
A FastMCP server mounted as a Starlette sub-application inside the FastAPI app
at ``/api/v1/mcp``.  Authentication uses the MCP SDK's ``BearerAuthBackend``
+ ``TokenVerifier``: API keys (``st_`` / ``mc_`` prefixes) are resolved against
the database via ``authenticate_token`` from ``backend.auth``.

Mount note
----------
``sse_app()`` returns a standalone Starlette ASGI application, not an APIRouter.
It must be mounted with ``app.mount()``, not ``app.include_router()``.
The SSE endpoint lives at ``/api/v1/mcp/sse`` and the messages POST endpoint at
``/api/v1/mcp/messages/``.

Follow-on tools
---------------
- ``stash_vfs_ls`` — list VFS directory contents.
- ``stash_vfs_cat`` — read VFS file contents.
- ``stash_session_upload`` — upload a session transcript to Stash.
- ``stash_memory_search`` — search Memory wiki pages by keyword.

Add new tools by decorating functions with ``@mcp.tool()`` in this module.
The auth layer is already wired — tool handlers access the authenticated user
via ``get_access_token()`` from ``mcp.server.auth.middleware.auth_context``.
"""

import json
import logging

from fastapi import HTTPException, status
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import AccessToken
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from backend.auth import authenticate_token
from backend.services import files_tree_service, source_service

logger = logging.getLogger("stash.mcp")

MCP_NAME = "stash"
MCP_VERSION = "0.x"
MCP_MOUNT_PATH = "/api/v1/mcp"

TOOL_INSTRUCTIONS = (
    "Stash — shared memory for AI coding agents. "
    "Authenticate with a Stash API key via the Authorization: Bearer header."
)

# ---------------------------------------------------------------------------
# Token verifier (MCP SDK TokenVerifier protocol)
# ---------------------------------------------------------------------------


class StashTokenVerifier(TokenVerifier):
    """Resolve a Stash API key (``st_`` / ``mc_``) to an ``AccessToken``.

    Protocol: ``mcp.server.auth.provider.TokenVerifier``
    - ``verify_token(self, token: str) -> AccessToken | None``
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = await authenticate_token(token)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                return None
            raise

        user_id = str(user["id"])
        return AccessToken(
            token=token,
            client_id=user_id,
            subject=user_id,
            scopes=["stash:full"],
            claims={
                "name": user.get("name", ""),
                "email": user.get("email", ""),
            },
        )


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

mcp = FastMCP(
    MCP_NAME,
    instructions=TOOL_INSTRUCTIONS,
    token_verifier=StashTokenVerifier(),
    auth=AuthSettings(
        issuer_url="https://joinstash.ai",
        resource_server_url="https://joinstash.ai/api/v1/mcp",
    ),
)


@mcp.tool()
async def get_stash_info() -> str:
    """Return identity info about the Stash server and authenticated user."""
    token: AccessToken | None = get_access_token()
    return json.dumps(
        {
            "name": MCP_NAME,
            "version": MCP_VERSION,
            "user_id": token.subject if token else "",
            "client_id": token.client_id if token else "",
            "scopes": list(token.scopes) if token else [],
        }
    )


@mcp.tool()
async def stash_search(query: str, limit: int = 10) -> str:
    """Search across all Stash content accessible to the authenticated user:
    native files, sessions, connected-source documents, and federated sources.

    Args:
        query: The search query string.
        limit: Maximum number of results to return (default 10).

    Returns:
        JSON string with a list of result objects, each containing
        source, ref, snippet, and optionally name / source_name keys.
    """
    token: AccessToken | None = get_access_token()
    user_id = token.subject if token else ""
    results = await source_service.search_all(user_id, user_id, query, limit=limit)
    if results is None:
        return json.dumps([])
    return json.dumps(results)


@mcp.tool()
async def stash_session_search(query: str, limit: int = 10) -> str:
    """Search the authenticated user's recent sessions by keyword.

    Performs full-text search across session transcript content (user
    messages, assistant messages, tool calls, etc.) and returns matching
    events with their session context. Results are scoped to sessions
    the authenticated user can read.

    Args:
        query: The search query string (keywords or natural-language
            phrases — uses PostgreSQL websearch syntax).
        limit: Maximum number of matching events to return (default 10).

    Returns:
        JSON string with keys:
          - query: The original search query.
          - count: Number of events returned.
          - results: Array of matching history event objects. Each event
            has session_id, agent_name, event_type, content (snippet),
            created_at, and rank fields.
    """
    from uuid import UUID

    from backend.services.memory_service import search_scope_events

    token: AccessToken | None = get_access_token()
    if token is None or not token.subject:
        return json.dumps({"error": "Authentication required"})

    user_id = UUID(token.subject)
    results = await search_scope_events(
        owner_user_id=user_id,
        user_id=user_id,
        query=query,
        limit=limit,
    )
    return json.dumps(
        {
            "query": query,
            "count": len(results),
            "results": results,
        },
        default=str,
    )


@mcp.tool()
async def stash_memory_search(
    query: str,
    scope: str | None = None,
    layer: str | None = None,
    limit: int = 5,
) -> str:
    """Search the authenticated user's Memory wiki pages by keyword.

    Performs full-text search across pages in the Memory folder subtree
    (the agent-curated wiki) and returns matching pages with name,
    content excerpt, and rank. Results are scoped to the authenticated
    user's own Memory folder.

    Args:
        query: The search query string (keywords or natural-language
            phrases — uses PostgreSQL websearch syntax).
        scope: Optional scope filter ("agent" or "project"). In Stash,
            all memory is per-user (project-scoped). Defaults to "project".
        layer: Optional layer filter ("long-term" or "daily"). In Stash,
            all memory pages are long-term wiki content. Defaults to
            "long-term".
        limit: Maximum number of results to return (default 5).

    Returns:
        JSON string with keys:
          - query: The original search query.
          - count: Number of results returned.
          - results: Array of matching page objects. Each page has id,
            name, folder_id, search_text (excerpt), content_type,
            updated_at, and rank fields.
    """
    from uuid import UUID

    token: AccessToken | None = get_access_token()
    if token is None or not token.subject:
        return json.dumps({"error": "Authentication required"})

    user_id = UUID(token.subject)
    results = await files_tree_service.search_pages_fts(
        owner_user_id=user_id,
        query=query,
        limit=limit,
        user_id=user_id,
    )

    out = []
    for r in results:
        entry = {
            "id": str(r["id"]),
            "name": r["name"],
            "folder_id": str(r["folder_id"]),
            "search_text": r["search_text"][:500] if r["search_text"] else "",
            "content_type": r["content_type"],
            "updated_at": str(r["updated_at"]),
            "rank": round(float(r["rank"]), 4),
        }
        out.append(entry)

    return json.dumps(
        {
            "query": query,
            "count": len(out),
            "results": out,
        },
        default=str,
    )


@mcp.tool()
async def stash_vfs_ls(path: str = "/") -> str:
    """List directory contents in Stash's virtual filesystem.

    Browse Stash as a single path-based filesystem. Start with
    ``stash_vfs_ls(path="/")`` to discover the top-level sections.

    VFS path format:
    - ``/`` — root, lists top-level sections (files, sessions, sources, memory, tables, skills)
    - ``/files/...`` — pages and uploaded files
    - ``/sources/<handle>/...`` — connected source documents
    - ``/sessions/...`` — agent session transcripts
    - ``/memory/...`` — agent-curated Memory wiki
    - ``/tables/...`` — table schemas and row data
    - ``/skills/...`` — published Skill folders

    Args:
        path: The VFS directory path to list (default: "/").

    Returns:
        JSON object with keys: path, is_dir, entries (sorted list of entry names),
        entry_count, type.
        On error: JSON object with keys: error (description), path.
    """
    import json

    from backend.main import app
    from backend.services.vfs_service import run_vfs_script

    token = get_access_token()
    if not token:
        return json.dumps({"error": "Authentication required"})

    authorization = f"Bearer {token.token}"
    result = await run_vfs_script(app, authorization, f"ls {path}", cwd="/")

    if result["exit_code"] != 0:
        return json.dumps(
            {
                "error": result["stderr"].strip(),
                "path": path,
            }
        )

    entries = [line.strip() for line in result["stdout"].split("\n") if line.strip()]
    return json.dumps(
        {
            "path": path,
            "is_dir": True,
            "entries": entries,
            "entry_count": len(entries),
            "type": "directory",
        }
    )


@mcp.tool()
async def stash_vfs_cat(path: str) -> str:
    """Read a file's contents from Stash's virtual filesystem.

    Read the text content of any file accessible via the VFS. Use
    ``stash_vfs_ls`` first to discover file paths.

    VFS path format:
    - ``/files/<page>.md`` — pages and uploaded files
    - ``/sources/<handle>/.../<file>`` — connected source documents
    - ``/sessions/...`` — agent session transcripts
    - ``/memory/...`` — agent-curated Memory wiki

    Args:
        path: The VFS file path to read.

    Returns:
        JSON object with keys: path, content (file contents), size (character count).
        For binary or missing files: JSON object with keys: error (description), path.
    """
    import json

    from backend.main import app
    from backend.services.vfs_service import run_vfs_script

    token = get_access_token()
    if not token:
        return json.dumps({"error": "Authentication required"})

    authorization = f"Bearer {token.token}"
    result = await run_vfs_script(app, authorization, f"cat {path}", cwd="/")

    if result["exit_code"] != 0:
        return json.dumps(
            {
                "error": result["stderr"].strip(),
                "path": path,
            }
        )

    content = result["stdout"]
    if not content:
        return json.dumps(
            {
                "error": "File is empty or binary — no text content returned",
                "path": path,
            }
        )

    return json.dumps(
        {
            "path": path,
            "content": content,
            "size": len(content),
        }
    )


@mcp.tool()
async def stash_session_upload(
    session_id: str,
    agent_name: str = "",
    cwd: str | None = None,
    events: str = "[]",
    replace: bool = False,
) -> str:
    """Upload a session transcript to Stash, making it searchable.

    Accepts session metadata and an array of event objects as a JSON
    string. Creates or updates the session row and inserts events.
    Uploaded sessions become immediately searchable via
    ``stash_session_search``.

    Args:
        session_id: Unique session identifier (e.g. ``sess_abc123``).
        agent_name: Name of the agent that recorded the session (e.g.
            ``claude-code``). Falls back to per-event ``agent_name``.
        cwd: Working directory for the session context.
        events: JSON string of an array of event objects. Each event may
            have: ``event_type`` (required), ``content`` (required),
            ``agent_name``, ``tool_name``, ``metadata``, ``created_at``.
        replace: If True and the session already has events, delete
            existing events before inserting the new ones (default False).

    Returns:
        JSON string with keys: ``session_id``, ``event_count`` (total events
        provided), ``imported`` (number of events inserted).
        On auth failure: ``{"error": "Authentication required"}``.
    """
    from uuid import UUID

    from backend.database import get_pool
    from backend.services import memory_service, session_service

    token: AccessToken | None = get_access_token()
    if token is None or not token.subject:
        return json.dumps({"error": "Authentication required"})

    user_id = UUID(token.subject)

    # Parse events JSON
    try:
        event_list = json.loads(events)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in events parameter"})

    if not isinstance(event_list, list):
        return json.dumps({"error": "events must be a JSON array"})

    # Fill in defaults per event
    for ev in event_list:
        if not ev.get("agent_name"):
            ev["agent_name"] = agent_name
        if not ev.get("session_id"):
            ev["session_id"] = session_id
        if "metadata" not in ev or ev["metadata"] is None:
            ev["metadata"] = {}

    # Validate required fields
    for i, ev in enumerate(event_list):
        if "event_type" not in ev or not ev["event_type"]:
            return json.dumps({"error": f"Event at index {i} missing required field: event_type"})
        if "content" not in ev or ev["content"] is None:
            return json.dumps({"error": f"Event at index {i} missing required field: content"})

    event_count = len(event_list)

    # Check for existing events
    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events WHERE owner_user_id = $1 AND session_id = $2",
        user_id,
        session_id,
    )

    if existing:
        if replace:
            await pool.execute(
                "DELETE FROM history_events WHERE owner_user_id = $1 AND session_id = $2",
                user_id,
                session_id,
            )
        else:
            # Idempotent: just upsert the session metadata and return
            await session_service.upsert_session(
                user_id,
                session_id,
                agent_name=agent_name,
                cwd=cwd,
                created_by=user_id,
            )
            return json.dumps(
                {
                    "session_id": session_id,
                    "event_count": event_count,
                    "imported": 0,
                    "skipped": True,
                    "reason": "session already has events",
                }
            )

    # Upsert session
    await session_service.upsert_session(
        user_id,
        session_id,
        agent_name=agent_name,
        cwd=cwd,
        created_by=user_id,
    )

    # Set cwd in event metadata if provided
    if cwd:
        for ev in event_list:
            meta = ev.get("metadata")
            if isinstance(meta, dict) and "cwd" not in meta:
                meta["cwd"] = cwd

    # Push events
    inserted = await memory_service.push_events_batch(user_id, user_id, event_list)

    return json.dumps(
        {
            "session_id": session_id,
            "event_count": event_count,
            "imported": len(inserted),
        }
    )


@mcp.tool()
async def stash_memory_append(
    scope: str,
    layer: str,
    content: str,
) -> str:
    """Append markdown content to the authenticated user's persistent Memory wiki in Stash.

    Each ``(scope, layer)`` pair maps to one page in the Memory folder
    (e.g. ``project-long-term``, ``agent-daily``).  If the page does not exist
    it is created; if it exists the new content is appended at the bottom
    with a timestamp heading separator.

    Args:
        scope: Which memory scope: ``"agent"`` or ``"project"``.
        layer: Which memory layer: ``"long-term"`` or ``"daily"``.
        content: Markdown content to append.

    Returns:
        JSON string with keys: ``page_id``, ``name``, ``action``
        (``"created"`` | ``"appended"``), ``app_url``.
    """
    import json
    from datetime import UTC, datetime
    from uuid import UUID

    from backend.database import get_pool

    VALID_SCOPES = {"agent", "project"}
    VALID_LAYERS = {"long-term", "daily"}

    # Validate parameters early
    if scope not in VALID_SCOPES:
        return json.dumps(
            {"error": f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}"}
        )
    if layer not in VALID_LAYERS:
        return json.dumps(
            {"error": f"Invalid layer '{layer}'. Must be one of: {', '.join(sorted(VALID_LAYERS))}"}
        )

    # Auth check
    token: AccessToken | None = get_access_token()
    if token is None or not token.subject:
        return json.dumps({"error": "Authentication required"})

    user_id = UUID(token.subject)

    # Resolve the memory folder
    memory = await files_tree_service.get_or_create_memory_folder(user_id, user_id)
    memory_folder_id = memory["id"]

    # Compute page name from scope + layer
    page_name = f"{scope}-{layer}"

    # Look for an existing page with that name in the memory folder
    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT id, owner_user_id, folder_id, name, content_markdown "
        "FROM pages WHERE owner_user_id = $1 AND folder_id = $2 AND name = $3 AND deleted_at IS NULL",
        user_id,
        memory_folder_id,
        page_name,
    )

    if existing:
        # Page exists — append content with timestamp separator
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        new_content = existing["content_markdown"] + f"\n\n## {ts}\n\n{content}"
        updated = await files_tree_service.update_page(
            page_id=existing["id"],
            owner_user_id=user_id,
            updated_by=user_id,
            content=new_content,
        )
        return json.dumps(
            {
                "page_id": str(existing["id"]),
                "name": page_name,
                "action": "appended",
                "app_url": updated.get("app_url", ""),
            }
        )

    # Page does not exist — create it
    page = await files_tree_service.create_page(
        owner_user_id=user_id,
        name=page_name,
        created_by=user_id,
        folder_id=memory_folder_id,
        content=content,
    )
    return json.dumps(
        {
            "page_id": str(page["id"]),
            "name": page_name,
            "action": "created",
            "app_url": page.get("app_url", ""),
        }
    )


# ---------------------------------------------------------------------------
# Factory — returns the Starlette ASGI sub-application
# ---------------------------------------------------------------------------


def create_mcp_app():
    """Build and return the MCP sub-application mounted in main.py.

    Notes
    -----
    We pass ``mount_path="/"`` so the MCP SDK does **not** prepend the
    mount prefix into its internal ``normalized_message_endpoint``  — doing so
    would cause the path to be duplicated because FastAPI's ``app.mount()``
    already sets ``root_path`` in the ASGI scope, and the SSE transport
    prepends that again.  With ``mount_path="/"`` the message path stays as
    ``/messages/`` and the actual mount prefix (``/api/v1/mcp``) is added
    exactly once — by FastAPI's mount machinery.
    """
    return mcp.sse_app(mount_path="/")
