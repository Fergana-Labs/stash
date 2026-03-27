"""Deck service: HTML/JS/CSS document CRUD with public share links."""

import secrets
from datetime import datetime
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
    token = secrets.token_urlsafe(12)[:12]
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
        "SELECT id, deck_id, token, name, is_active, require_email, "
        "passcode_hash IS NOT NULL AS has_passcode, allow_download, expires_at, created_at "
        "FROM deck_shares WHERE deck_id = $1 ORDER BY created_at DESC",
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
