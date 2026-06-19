"""User scope service: provisioning and CRUD for the single per-user scope.

Each user owns exactly one scope. There is no membership, joining, or invites —
the owner is the creator, and access for anyone else flows through `shares`.

(Transitional note: the scope is still stored in the `workspaces` table and its
`workspace_id` foreign keys; those names are renamed away in a later cleanup
migration.)
"""

import logging
import secrets
from uuid import UUID

from ..database import get_pool
from . import skill_seeds

logger = logging.getLogger(__name__)


async def create_workspace(
    name: str,
    description: str,
    creator_id: UUID,
) -> dict:
    """Provision a user's scope, owned by the creator."""
    pool = get_pool()
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        exists = await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1",
            invite_code,
        )
        if not exists:
            break

    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, description, creator_id, invite_code) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, name, description, creator_id, invite_code, "
        "created_at, updated_at, cover_image_url, icon_url, color_gradient",
        name,
        description,
        creator_id,
        invite_code,
    )
    ws = dict(row)
    ws["member_count"] = 1
    # Seed the default slides skill so the agent can discover it via
    # list_skills/read_skill when the user asks for a deck. Failures here should
    # not block scope creation.
    try:
        await skill_seeds.seed_slides_skill(ws["id"], creator_id)
    except Exception:
        logger.exception("seed_slides_skill failed for scope %s", ws["id"])
    return ws


async def get_primary_for_user(user_id: UUID) -> UUID | None:
    """The user's one scope id, or None if they have none."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM workspaces WHERE creator_id = $1 ORDER BY created_at LIMIT 1",
        user_id,
    )
    return row["id"] if row else None


async def get_workspace(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, description, creator_id, invite_code, "
        "created_at, updated_at, cover_image_url, icon_url, color_gradient, "
        "1 AS member_count "
        "FROM workspaces WHERE id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def list_user_workspaces(user_id: UUID) -> list[dict]:
    """The user's single scope, as a one-element list (the owner is the creator)."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, description, creator_id, invite_code, "
        "created_at, updated_at, cover_image_url, icon_url, color_gradient, "
        "TRUE AS is_primary, 1 AS member_count "
        "FROM workspaces WHERE creator_id = $1 ORDER BY created_at",
        user_id,
    )
    return [dict(r) for r in rows]


async def update_workspace(
    workspace_id: UUID,
    name: str | None = None,
    description: str | None = None,
    cover_image_url: str | None = None,
    icon_url: str | None = None,
    color_gradient: str | None = None,
) -> dict | None:
    pool = get_pool()
    sets, args, idx = [], [], 1
    for col, val in (
        ("name", name),
        ("description", description),
        ("cover_image_url", cover_image_url),
        ("icon_url", icon_url),
        ("color_gradient", color_gradient),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1
    if not sets:
        return await get_workspace(workspace_id)
    sets.append("updated_at = now()")
    args.append(workspace_id)
    await pool.execute(
        f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ${idx}",
        *args,
    )
    return await get_workspace(workspace_id)


async def delete_workspace(workspace_id: UUID, user_id: UUID) -> list[str] | None:
    """Delete a scope (owner only; None when refused). Returns the storage keys
    its rows referenced so the caller can purge the blobs — collected before, but
    purged only after, the DB delete, so a failed delete can never leave live
    rows pointing at destroyed storage objects."""
    pool = get_pool()
    if not await is_owner(workspace_id, user_id):
        return None

    # Forks copy storage_key by reference (shared_skill_service._fork_file /
    # _fork_session), so one S3 object can back rows in several scopes. Only
    # return keys referenced solely by this scope; deleting a key another scope
    # still points at would 502 their downloads.
    rows = await pool.fetch(
        """
        SELECT k.storage_key
        FROM (
            SELECT storage_key
            FROM files
            WHERE workspace_id = $1

            UNION

            SELECT sa.storage_key
            FROM session_artifacts sa
            JOIN sessions s ON s.id = sa.session_id
            WHERE s.workspace_id = $1
        ) k
        WHERE NOT EXISTS (
            SELECT 1 FROM files f
            WHERE f.storage_key = k.storage_key AND f.workspace_id <> $1
        )
        AND NOT EXISTS (
            SELECT 1 FROM session_artifacts sa2
            JOIN sessions s2 ON s2.id = sa2.session_id
            WHERE sa2.storage_key = k.storage_key AND s2.workspace_id <> $1
        )
        ORDER BY k.storage_key
        """,
        workspace_id,
    )
    result = await pool.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
    if result != "DELETE 1":
        return None
    return [row["storage_key"] for row in rows]


# --- Ownership helpers (the only role is "owner": the scope's creator) ---

ROLES_CAN_READ = {"owner"}
ROLES_CAN_WRITE = {"owner"}
ROLES_ADMIN = {"owner"}


async def get_member_role(workspace_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM workspaces WHERE id = $1 AND creator_id = $2",
        workspace_id,
        user_id,
    )
    return "owner" if row else None


async def is_member(workspace_id: UUID, user_id: UUID) -> bool:
    return await get_member_role(workspace_id, user_id) is not None


async def get_members(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id AS user_id, u.name, u.display_name, 'owner' AS role, "
        "w.created_at AS joined_at "
        "FROM workspaces w JOIN users u ON u.id = w.creator_id WHERE w.id = $1",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def can_read(workspace_id: UUID, user_id: UUID) -> bool:
    return await is_member(workspace_id, user_id)


async def can_write(workspace_id: UUID, user_id: UUID) -> bool:
    return await is_member(workspace_id, user_id)


async def is_owner(workspace_id: UUID, user_id: UUID) -> bool:
    return await is_member(workspace_id, user_id)
