"""Deck service: HTML/JS/CSS document CRUD, public share links, viewer analytics."""

import secrets
from datetime import datetime, timezone
from uuid import UUID

import bcrypt

from ..database import get_pool


# --- Deck CRUD ---


async def create_deck(
    workspace_id: UUID | None, name: str, description: str,
    html_content: str, deck_type: str, created_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO decks (workspace_id, name, description, html_content, deck_type, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $6) "
        "RETURNING id, workspace_id, name, description, html_content, deck_type, "
        "created_by, updated_by, created_at, updated_at",
        workspace_id, name, description, html_content, deck_type, created_by,
    )
    return dict(row)


async def get_deck(deck_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, description, html_content, deck_type, "
        "created_by, updated_by, created_at, updated_at FROM decks WHERE id = $1",
        deck_id,
    )
    return dict(row) if row else None


async def update_deck(
    deck_id: UUID, updated_by: UUID,
    name: str | None = None, description: str | None = None,
    html_content: str | None = None,
) -> dict | None:
    pool = get_pool()
    sets = ["updated_at = now()", "updated_by = $1"]
    args: list = [updated_by]
    idx = 2

    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        args.append(description)
        idx += 1
    if html_content is not None:
        sets.append(f"html_content = ${idx}")
        args.append(html_content)
        idx += 1

    args.append(deck_id)
    row = await pool.fetchrow(
        f"UPDATE decks SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, workspace_id, name, description, html_content, deck_type, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    return dict(row) if row else None


async def delete_deck(deck_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM decks WHERE id = $1", deck_id)
    return result == "DELETE 1"


async def list_decks(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, name, description, html_content, deck_type, "
        "created_by, updated_by, created_at, updated_at "
        "FROM decks WHERE workspace_id = $1 ORDER BY updated_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def list_personal_decks(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, name, description, html_content, deck_type, "
        "created_by, updated_by, created_at, updated_at "
        "FROM decks WHERE workspace_id IS NULL AND created_by = $1 ORDER BY updated_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def list_all_user_decks(user_id: UUID) -> list[dict]:
    """All decks from workspaces user is member of + personal."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT d.id, d.workspace_id, d.name, d.description, d.deck_type, "
        "d.created_by, d.updated_by, d.created_at, d.updated_at, "
        "w.name AS workspace_name "
        "FROM decks d "
        "LEFT JOIN workspaces w ON w.id = d.workspace_id "
        "WHERE d.workspace_id IN ("
        "  SELECT workspace_id FROM workspace_members WHERE user_id = $1"
        ") OR (d.workspace_id IS NULL AND d.created_by = $1) "
        "ORDER BY d.updated_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


# --- Share Links ---


async def create_share_link(
    deck_id: UUID, created_by: UUID,
    name: str | None = None, require_email: bool = False,
    passcode: str | None = None, allow_download: bool = True,
    expires_at: str | None = None,
) -> dict:
    pool = get_pool()
    token = secrets.token_urlsafe(9)[:12]
    passcode_hash = bcrypt.hashpw(passcode.encode(), bcrypt.gensalt()).decode() if passcode else None
    exp = datetime.fromisoformat(expires_at) if expires_at else None

    row = await pool.fetchrow(
        "INSERT INTO deck_shares (deck_id, token, name, is_active, require_email, "
        "passcode_hash, allow_download, expires_at, created_by) "
        "VALUES ($1, $2, $3, true, $4, $5, $6, $7, $8) "
        "RETURNING id, deck_id, token, name, is_active, require_email, "
        "passcode_hash, allow_download, expires_at, created_by, created_at",
        deck_id, token, name, require_email, passcode_hash, allow_download, exp, created_by,
    )
    share = dict(row)
    share["has_passcode"] = share.pop("passcode_hash") is not None
    return share


async def update_share_link(
    share_id: UUID,
    name: str | None = None, is_active: bool | None = None,
    require_email: bool | None = None, passcode: str | None = None,
    clear_passcode: bool = False, allow_download: bool | None = None,
    expires_at: str | None = None, clear_expires: bool = False,
) -> dict | None:
    pool = get_pool()
    sets: list[str] = []
    args: list = []
    idx = 1

    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if is_active is not None:
        sets.append(f"is_active = ${idx}")
        args.append(is_active)
        idx += 1
    if require_email is not None:
        sets.append(f"require_email = ${idx}")
        args.append(require_email)
        idx += 1
    if passcode:
        h = bcrypt.hashpw(passcode.encode(), bcrypt.gensalt()).decode()
        sets.append(f"passcode_hash = ${idx}")
        args.append(h)
        idx += 1
    elif clear_passcode:
        sets.append("passcode_hash = NULL")
    if allow_download is not None:
        sets.append(f"allow_download = ${idx}")
        args.append(allow_download)
        idx += 1
    if expires_at:
        sets.append(f"expires_at = ${idx}")
        args.append(datetime.fromisoformat(expires_at))
        idx += 1
    elif clear_expires:
        sets.append("expires_at = NULL")

    if not sets:
        return await _get_share(share_id)

    args.append(share_id)
    row = await pool.fetchrow(
        f"UPDATE deck_shares SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, deck_id, token, name, is_active, require_email, "
        "passcode_hash IS NOT NULL AS has_passcode, allow_download, expires_at, created_at",
        *args,
    )
    return dict(row) if row else None


async def _get_share(share_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, deck_id, token, name, is_active, require_email, "
        "passcode_hash IS NOT NULL AS has_passcode, allow_download, expires_at, created_at "
        "FROM deck_shares WHERE id = $1",
        share_id,
    )
    return dict(row) if row else None


async def get_share_by_token(token: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ds.id, ds.deck_id, ds.token, ds.name, ds.is_active, ds.require_email, "
        "ds.passcode_hash, ds.allow_download, ds.expires_at, ds.created_at, "
        "d.name AS deck_name, d.html_content, d.deck_type "
        "FROM deck_shares ds JOIN decks d ON d.id = ds.deck_id "
        "WHERE ds.token = $1 AND ds.is_active = true",
        token,
    )
    return dict(row) if row else None


async def list_share_links(deck_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ds.id, ds.deck_id, ds.token, ds.name, ds.is_active, ds.require_email, "
        "ds.passcode_hash IS NOT NULL AS has_passcode, ds.allow_download, ds.expires_at, ds.created_at, "
        "(SELECT COUNT(*) FROM deck_share_views dsv WHERE dsv.share_id = ds.id) AS view_count "
        "FROM deck_shares ds WHERE ds.deck_id = $1 ORDER BY ds.created_at DESC",
        deck_id,
    )
    return [dict(r) for r in rows]


async def deactivate_share_link(share_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE deck_shares SET is_active = false WHERE id = $1", share_id,
    )
    return result == "UPDATE 1"


async def verify_passcode(share: dict, passcode: str) -> bool:
    if not share.get("passcode_hash"):
        return True
    return bcrypt.checkpw(passcode.encode(), share["passcode_hash"].encode())


# --- Viewer Tracking ---


async def create_view_session(
    share_id: UUID, viewer_email: str | None = None,
    viewer_ip: str | None = None, user_agent: str | None = None,
) -> dict:
    pool = get_pool()
    session_token = secrets.token_urlsafe(48)
    row = await pool.fetchrow(
        "INSERT INTO deck_share_views (share_id, session_token, viewer_email, viewer_ip, user_agent) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id, share_id, session_token, viewer_email, started_at, last_active_at, total_duration_seconds",
        share_id, session_token, viewer_email, viewer_ip, user_agent,
    )
    return dict(row)


async def get_view_by_session(session_token: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, share_id, session_token, viewer_email, started_at, last_active_at, total_duration_seconds "
        "FROM deck_share_views WHERE session_token = $1",
        session_token,
    )
    return dict(row) if row else None


async def heartbeat(session_token: str, page_identifier: str | None = None) -> None:
    """Update viewer session and optionally track page engagement."""
    pool = get_pool()
    view = await get_view_by_session(session_token)
    if not view:
        return

    # Calculate elapsed since last heartbeat (cap at 60s to ignore idle)
    now = datetime.now(timezone.utc)
    last = view["last_active_at"]
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = min(int((now - last).total_seconds()), 60)

    await pool.execute(
        "UPDATE deck_share_views SET last_active_at = now(), "
        "total_duration_seconds = total_duration_seconds + $1 WHERE id = $2",
        elapsed, view["id"],
    )

    if page_identifier:
        await pool.execute(
            "INSERT INTO deck_share_page_views (view_id, page_identifier, duration_seconds) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (view_id, page_identifier) DO UPDATE SET "
            "duration_seconds = deck_share_page_views.duration_seconds + $3",
            view["id"], page_identifier, elapsed,
        )


# --- Analytics ---


async def get_share_analytics(share_id: UUID) -> dict:
    pool = get_pool()

    # Viewer sessions
    viewers = await pool.fetch(
        "SELECT id, viewer_email, viewer_ip, started_at, last_active_at, total_duration_seconds "
        "FROM deck_share_views WHERE share_id = $1 ORDER BY started_at DESC",
        share_id,
    )

    # Aggregate stats
    total_views = len(viewers)
    unique_emails = set()
    unique_ips = set()
    total_duration = 0
    for v in viewers:
        if v["viewer_email"]:
            unique_emails.add(v["viewer_email"])
        elif v["viewer_ip"]:
            unique_ips.add(v["viewer_ip"])
        total_duration += v["total_duration_seconds"]
    unique_viewers = len(unique_emails) + len(unique_ips)
    if unique_viewers == 0:
        unique_viewers = total_views  # fallback

    avg_duration = total_duration // total_views if total_views > 0 else 0

    # Page-level stats
    page_stats = await pool.fetch(
        "SELECT page_identifier, SUM(duration_seconds) AS total_seconds, COUNT(*) AS view_count "
        "FROM deck_share_page_views WHERE view_id IN ("
        "  SELECT id FROM deck_share_views WHERE share_id = $1"
        ") GROUP BY page_identifier ORDER BY page_identifier",
        share_id,
    )

    return {
        "total_views": total_views,
        "unique_viewers": unique_viewers,
        "avg_duration_seconds": avg_duration,
        "viewers": [
            {
                "id": v["id"],
                "viewer_email": v["viewer_email"],
                "viewer_ip": v["viewer_ip"],
                "started_at": v["started_at"],
                "last_active_at": v["last_active_at"],
                "total_duration_seconds": v["total_duration_seconds"],
            }
            for v in viewers
        ],
        "page_stats": [dict(p) for p in page_stats],
    }
