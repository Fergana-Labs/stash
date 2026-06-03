"""In-product Stash invitations."""

from uuid import UUID

from ..database import get_pool


async def create_or_update_invite(
    *,
    cartridge_id: UUID,
    recipient_user_id: UUID,
    invited_by_user_id: UUID,
    permission: str,
) -> dict | None:
    if recipient_user_id == invited_by_user_id:
        return None

    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cartridge_invites
          (cartridge_id, recipient_user_id, invited_by_user_id, permission, status,
           target_workspace_id, responded_at)
        VALUES ($1, $2, $3, $4, 'pending', NULL, NULL)
        ON CONFLICT (cartridge_id, recipient_user_id) DO UPDATE
        SET invited_by_user_id = EXCLUDED.invited_by_user_id,
            permission = EXCLUDED.permission,
            status = 'pending',
            target_workspace_id = NULL,
            responded_at = NULL,
            updated_at = now()
        RETURNING id, cartridge_id, recipient_user_id, invited_by_user_id, permission,
                  status, target_workspace_id, created_at, updated_at, responded_at
        """,
        cartridge_id,
        recipient_user_id,
        invited_by_user_id,
        permission,
    )
    return dict(row) if row else None


async def delete_pending_invite(cartridge_id: UUID, recipient_user_id: UUID) -> None:
    pool = get_pool()
    await pool.execute(
        "DELETE FROM cartridge_invites "
        "WHERE cartridge_id = $1 AND recipient_user_id = $2 AND status = 'pending'",
        cartridge_id,
        recipient_user_id,
    )


async def list_pending_invites(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT si.id,
               si.cartridge_id,
               s.slug AS cartridge_slug,
               s.title AS cartridge_title,
               s.description AS cartridge_description,
               s.workspace_id AS source_workspace_id,
               w.name AS source_workspace_name,
               si.invited_by_user_id,
               u.name AS invited_by_name,
               u.display_name AS invited_by_display_name,
               si.permission,
               si.created_at
        FROM cartridge_invites si
        JOIN cartridges s ON s.id = si.cartridge_id
        JOIN workspaces w ON w.id = s.workspace_id
        JOIN users u ON u.id = si.invited_by_user_id
        WHERE si.recipient_user_id = $1
          AND si.status = 'pending'
        ORDER BY si.created_at DESC, si.id DESC
        """,
        user_id,
    )
    return [dict(row) for row in rows]


async def mark_invite_accepted_for_cartridge(
    *,
    cartridge_id: UUID,
    user_id: UUID,
    workspace_id: UUID,
) -> None:
    pool = get_pool()
    await pool.execute(
        """
        UPDATE cartridge_invites
        SET status = 'accepted',
            target_workspace_id = $1,
            responded_at = now(),
            updated_at = now()
        WHERE cartridge_id = $2
          AND recipient_user_id = $3
          AND status = 'pending'
        """,
        workspace_id,
        cartridge_id,
        user_id,
    )


async def dismiss_invite(invite_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        """
        UPDATE cartridge_invites
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
