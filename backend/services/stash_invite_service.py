"""In-product Stash invitations."""

from uuid import UUID

from ..database import get_pool
from . import stash_service, workspace_service


async def create_or_update_invite(
    *,
    stash_id: UUID,
    recipient_user_id: UUID,
    invited_by_user_id: UUID,
    permission: str,
) -> dict | None:
    if recipient_user_id == invited_by_user_id:
        return None

    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO stash_invites
          (stash_id, recipient_user_id, invited_by_user_id, permission, status,
           target_workspace_id, responded_at)
        VALUES ($1, $2, $3, $4, 'pending', NULL, NULL)
        ON CONFLICT (stash_id, recipient_user_id) DO UPDATE
        SET invited_by_user_id = EXCLUDED.invited_by_user_id,
            permission = EXCLUDED.permission,
            status = 'pending',
            target_workspace_id = NULL,
            responded_at = NULL,
            updated_at = now()
        RETURNING id, stash_id, recipient_user_id, invited_by_user_id, permission,
                  status, target_workspace_id, created_at, updated_at, responded_at
        """,
        stash_id,
        recipient_user_id,
        invited_by_user_id,
        permission,
    )
    return dict(row) if row else None


async def delete_pending_invite(stash_id: UUID, recipient_user_id: UUID) -> None:
    pool = get_pool()
    await pool.execute(
        "DELETE FROM stash_invites "
        "WHERE stash_id = $1 AND recipient_user_id = $2 AND status = 'pending'",
        stash_id,
        recipient_user_id,
    )


async def list_pending_invites(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT si.id,
               si.stash_id,
               s.slug AS stash_slug,
               s.title AS stash_title,
               s.description AS stash_description,
               s.workspace_id AS source_workspace_id,
               w.name AS source_workspace_name,
               si.invited_by_user_id,
               u.name AS invited_by_name,
               u.display_name AS invited_by_display_name,
               si.permission,
               si.created_at
        FROM stash_invites si
        JOIN stashes s ON s.id = si.stash_id
        JOIN workspaces w ON w.id = s.workspace_id
        JOIN users u ON u.id = si.invited_by_user_id
        WHERE si.recipient_user_id = $1
          AND si.status = 'pending'
        ORDER BY si.created_at DESC, si.id DESC
        """,
        user_id,
    )
    return [dict(row) for row in rows]


async def accept_invite(invite_id: UUID, user_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    invite = await pool.fetchrow(
        """
        SELECT si.id, si.stash_id, s.slug
        FROM stash_invites si
        JOIN stashes s ON s.id = si.stash_id
        WHERE si.id = $1
          AND si.recipient_user_id = $2
          AND si.status = 'pending'
        """,
        invite_id,
        user_id,
    )
    if not invite:
        return None

    if not await workspace_service.is_member(workspace_id, user_id):
        raise PermissionError("Not a workspace member")

    stash = await stash_service.add_external_stash(workspace_id, invite["slug"], user_id)
    if not stash:
        return None

    await pool.execute(
        """
        UPDATE stash_invites
        SET status = 'accepted',
            target_workspace_id = $1,
            responded_at = now(),
            updated_at = now()
        WHERE id = $2
          AND recipient_user_id = $3
        """,
        workspace_id,
        invite_id,
        user_id,
    )
    return stash


async def dismiss_invite(invite_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        """
        UPDATE stash_invites
        SET status = 'dismissed',
            responded_at = now(),
            updated_at = now()
        WHERE id = $1
          AND recipient_user_id = $2
          AND status = 'pending'
        """,
        invite_id,
        user_id,
    )
    return result == "UPDATE 1"
