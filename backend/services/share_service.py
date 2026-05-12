"""Share-link minting + polymorphic recipient projection.

A share link wraps ONE target: a workspace, a session, a page, a folder,
or a file. Default intent is viewing; creator can grant edit. Time-
limitable, revocable.

The per-resource `public_in_share` flag is gone — sharing is now link-
based, not resource-flag-based.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..config import settings
from ..database import get_pool

VALID_TARGETS = {"workspace", "session", "page", "folder", "file"}
VALID_PERMISSIONS = {"view", "edit"}


def _new_token() -> str:
    return secrets.token_urlsafe(16)  # 22 url-safe chars


async def create_link(
    *,
    workspace_id: UUID,
    creator_id: UUID,
    target_type: str,
    target_id: UUID,
    ttl_days: int | None,
    permission: str = "view",
    slug: str | None = None,
) -> dict:
    if target_type not in VALID_TARGETS:
        raise ValueError(f"target_type must be one of {VALID_TARGETS}")
    if permission not in VALID_PERMISSIONS:
        raise ValueError(f"permission must be one of {VALID_PERMISSIONS}")

    pool = get_pool()
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None
    token = _new_token()
    row = await pool.fetchrow(
        "INSERT INTO share_links "
        "(token, workspace_id, created_by, expires_at, permission, target_type, target_id, slug) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "RETURNING token, workspace_id, created_by, created_at, expires_at, permission, "
        "view_count, target_type, target_id, slug",
        token,
        workspace_id,
        creator_id,
        expires_at,
        permission,
        target_type,
        target_id,
        slug,
    )
    out = dict(row)
    out["url"] = f"{settings.PUBLIC_URL.rstrip('/')}/share/{out['slug'] or out['token']}"
    return out


async def list_links(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT token, workspace_id, created_by, created_at, expires_at, permission, "
        "view_count, last_viewed_at, target_type, target_id, slug "
        "FROM share_links WHERE workspace_id = $1 AND revoked_at IS NULL "
        "ORDER BY created_at DESC",
        workspace_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["url"] = f"{settings.PUBLIC_URL.rstrip('/')}/share/{d['slug'] or d['token']}"
        out.append(d)
    return out


async def revoke_link(token: str, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE share_links SET revoked_at = now() "
        "WHERE token = $1 AND workspace_id = $2 AND revoked_at IS NULL",
        token,
        workspace_id,
    )
    return result.endswith(" 1")


async def resolve_token(token_or_slug: str) -> dict:
    """Resolve a share by token (opaque) or slug (URL-friendly).

    Returns {'status': 'ok' | 'expired' | 'revoked' | 'missing', 'link': ...}.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT token, workspace_id, created_by, created_at, expires_at, permission, "
        "view_count, revoked_at, target_type, target_id, slug "
        "FROM share_links WHERE token = $1 OR slug = $1",
        token_or_slug,
    )
    if not row:
        return {"status": "missing"}
    if row["revoked_at"]:
        return {"status": "revoked"}
    if row["expires_at"] and row["expires_at"] < datetime.now(UTC):
        return {"status": "expired"}
    return {"status": "ok", "link": dict(row)}


async def record_view(token: str, viewer_user_id: UUID | None) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE share_links "
        "SET view_count = view_count + 1, last_viewed_at = now(), last_viewed_by = $2 "
        "WHERE token = $1 OR slug = $1",
        token,
        viewer_user_id,
    )


_SLIDE_SPLIT = re.compile(r"^\s*---+\s*$", re.MULTILINE)


def _parse_deck(narrative_md: str) -> list[dict] | None:
    if not narrative_md:
        return None
    parts = [p.strip() for p in _SLIDE_SPLIT.split(narrative_md) if p.strip()]
    if len(parts) < 2:
        return None
    slides = []
    for i, part in enumerate(parts):
        lines = part.splitlines()
        title = ""
        body_lines = lines
        for j, ln in enumerate(lines):
            stripped = ln.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                body_lines = lines[j + 1 :]
                break
        slides.append({
            "index": i,
            "title": title or f"Slide {i + 1}",
            "kicker": f"{i + 1:02d} / {len(parts):02d}",
            "body": "\n".join(body_lines).strip(),
        })
    return slides


async def _workspace_projection(workspace_id: UUID) -> dict:
    """Full workspace projection — used both for target_type='workspace' and
    as the outer shell for narrower targets."""
    pool = get_pool()
    ws = await pool.fetchrow(
        "SELECT id, name, description, summary, cover_image_url, creator_id, created_at "
        "FROM workspaces WHERE id = $1",
        workspace_id,
    )
    if not ws:
        return {}
    creator = await pool.fetchrow(
        "SELECT name, display_name FROM users WHERE id = $1", ws["creator_id"]
    )
    # Show pages + files in the workspace (whole-stash share = everything visible).
    pages = await pool.fetch(
        "SELECT id, name, folder_id, content_markdown, updated_at FROM pages "
        "WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )
    files = await pool.fetch(
        "SELECT id, name, folder_id, content_type, size_bytes, created_at FROM files "
        "WHERE workspace_id = $1 ORDER BY created_at DESC",
        workspace_id,
    )
    return {
        "stash": {
            "id": str(ws["id"]),
            "name": ws["name"],
            "description": ws["description"],
            "summary": ws["summary"],
            "cover_image_url": ws["cover_image_url"],
            "creator": {
                "name": creator["name"] if creator else "—",
                "display_name": creator["display_name"] if creator else None,
            },
        },
        "pages": [
            {
                "id": str(p["id"]),
                "name": p["name"],
                "folder_id": str(p["folder_id"]) if p["folder_id"] else None,
                "body": p["content_markdown"] or "",
            }
            for p in pages
        ],
        "files": [
            {
                "id": str(f["id"]),
                "name": f["name"],
                "folder_id": str(f["folder_id"]) if f["folder_id"] else None,
                "content_type": f["content_type"],
                "size_bytes": f["size_bytes"],
            }
            for f in files
        ],
    }


async def _session_projection(session_row_id: UUID) -> dict:
    """Projection for a session-target share: session metadata + artifacts +
    chat thread reconstructed from history_events."""
    pool = get_pool()
    from . import memory_service

    s = await pool.fetchrow(
        "SELECT id, workspace_id, session_id, agent_name, cwd, summary, status, "
        "files_touched, started_at, finished_at "
        "FROM sessions WHERE id = $1",
        session_row_id,
    )
    if not s:
        return {}
    artifacts = await pool.fetch(
        "SELECT id, file_path, size_bytes, created_at "
        "FROM session_artifacts WHERE session_id = $1 ORDER BY file_path",
        session_row_id,
    )
    events = await memory_service.read_session_events(s["workspace_id"], s["session_id"])
    return {
        "session": {
            "id": str(s["id"]),
            "session_id": s["session_id"],
            "agent_name": s["agent_name"],
            "cwd": s["cwd"],
            "summary": s["summary"],
            "status": s["status"],
            "files_touched": s["files_touched"],
            "started_at": s["started_at"],
            "finished_at": s["finished_at"],
        },
        "artifacts": [
            {
                "id": str(a["id"]),
                "file_path": a["file_path"],
                "size_bytes": a["size_bytes"],
            }
            for a in artifacts
        ],
        "events": [
            {
                "id": str(e["id"]),
                "role": "user" if e["event_type"] == "user_message"
                        else "assistant",
                "content": e["content"] or "",
                "tool_name": e["tool_name"],
                "created_at": e["created_at"].isoformat() if e["created_at"] else None,
            }
            for e in events
            if e["event_type"] in ("user_message", "assistant_message", "tool_use")
        ],
    }


async def _page_projection(page_id: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, content_markdown, content_html, content_type, "
        "folder_id, updated_at "
        "FROM pages WHERE id = $1",
        page_id,
    )
    if not row:
        return {}
    return {
        "page": {
            "id": str(row["id"]),
            "name": row["name"],
            "body": row["content_markdown"] or "",
            "content_html": row["content_html"] or "",
            "content_type": row["content_type"],
            "folder_id": str(row["folder_id"]) if row["folder_id"] else None,
        }
    }


async def _folder_projection(folder_id: UUID) -> dict:
    pool = get_pool()
    folder = await pool.fetchrow(
        "SELECT id, workspace_id, name, parent_folder_id FROM folders WHERE id = $1",
        folder_id,
    )
    if not folder:
        return {}
    subfolders = await pool.fetch(
        "SELECT id, name FROM folders WHERE parent_folder_id = $1 ORDER BY name",
        folder_id,
    )
    pages = await pool.fetch(
        "SELECT id, name FROM pages WHERE folder_id = $1 ORDER BY name",
        folder_id,
    )
    files = await pool.fetch(
        "SELECT id, name, content_type, size_bytes FROM files "
        "WHERE folder_id = $1 ORDER BY created_at DESC",
        folder_id,
    )
    return {
        "folder": {
            "id": str(folder["id"]),
            "name": folder["name"],
            "parent_folder_id": str(folder["parent_folder_id"]) if folder["parent_folder_id"] else None,
        },
        "subfolders": [{"id": str(r["id"]), "name": r["name"]} for r in subfolders],
        "pages": [{"id": str(r["id"]), "name": r["name"]} for r in pages],
        "files": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "content_type": r["content_type"],
                "size_bytes": r["size_bytes"],
            }
            for r in files
        ],
    }


async def _file_projection(file_id: UUID) -> dict:
    pool = get_pool()
    from . import storage_service

    row = await pool.fetchrow(
        "SELECT id, name, content_type, size_bytes, storage_key, folder_id "
        "FROM files WHERE id = $1",
        file_id,
    )
    if not row:
        return {}
    try:
        url = await storage_service.get_file_url(row["storage_key"])
    except Exception:
        url = None
    return {
        "file": {
            "id": str(row["id"]),
            "name": row["name"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "url": url,
            "folder_id": str(row["folder_id"]) if row["folder_id"] else None,
        }
    }


async def public_projection(link: dict) -> dict:
    """Build the recipient projection for a share link. Dispatches by target_type.

    The returned dict always carries `share` (link metadata) + a payload
    keyed by target_type — `workspace` / `session` / `page` / `folder` /
    `file` block on top of it.
    """
    target_type = link.get("target_type") or "workspace"
    target_id = link.get("target_id") or link.get("workspace_id")
    workspace_id = link.get("workspace_id")

    if target_type == "workspace":
        payload = await _workspace_projection(target_id)
    elif target_type == "session":
        payload = await _session_projection(target_id)
    elif target_type == "page":
        payload = await _page_projection(target_id)
        payload.setdefault("stash", (await _workspace_projection(workspace_id)).get("stash"))
    elif target_type == "folder":
        payload = await _folder_projection(target_id)
        payload.setdefault("stash", (await _workspace_projection(workspace_id)).get("stash"))
    elif target_type == "file":
        payload = await _file_projection(target_id)
        payload.setdefault("stash", (await _workspace_projection(workspace_id)).get("stash"))
    else:
        payload = {}

    payload["share"] = {
        "token": link.get("token"),
        "slug": link.get("slug"),
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "permission": link.get("permission") or "view",
        "expires_at": link.get("expires_at"),
        "view_count": link.get("view_count", 0),
        "created_at": link.get("created_at"),
    }
    return payload
