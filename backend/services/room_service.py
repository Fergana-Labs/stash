import secrets
from uuid import UUID

from ..database import get_pool


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(6)[:8]


async def create_room(
    name: str, description: str, creator_id: UUID, is_public: bool = True
) -> dict:
    pool = get_pool()
    invite_code = _generate_invite_code()
    # Retry if invite code collision (unlikely)
    for _ in range(5):
        try:
            row = await pool.fetchrow(
                "INSERT INTO rooms (name, description, creator_id, invite_code, is_public) "
                "VALUES ($1, $2, $3, $4, $5) "
                "RETURNING id, name, description, creator_id, invite_code, is_public, matrix_room_id, created_at",
                name,
                description,
                creator_id,
                invite_code,
                is_public,
            )
            break
        except Exception as e:
            if "invite_code" in str(e).lower() and "unique" in str(e).lower():
                invite_code = _generate_invite_code()
                continue
            raise
    else:
        raise RuntimeError("Failed to generate unique invite code")

    # Auto-join creator as owner
    await pool.execute(
        "INSERT INTO room_members (room_id, user_id, role) VALUES ($1, $2, 'owner')",
        row["id"],
        creator_id,
    )
    result = dict(row)
    result["member_count"] = 1
    return result


async def get_room(room_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT r.*, (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) AS member_count "
        "FROM rooms r WHERE r.id = $1",
        room_id,
    )
    return dict(row) if row else None


async def get_room_by_invite_code(invite_code: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT r.*, (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) AS member_count "
        "FROM rooms r WHERE r.invite_code = $1",
        invite_code,
    )
    return dict(row) if row else None


async def list_public_rooms() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT r.*, (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) AS member_count "
        "FROM rooms r WHERE r.is_public = true ORDER BY r.created_at DESC"
    )
    return [dict(r) for r in rows]


async def list_user_rooms(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT r.*, (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) AS member_count "
        "FROM rooms r INNER JOIN room_members rm ON r.id = rm.room_id "
        "WHERE rm.user_id = $1 ORDER BY r.created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def join_room(room_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT 1 FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    if existing:
        return False  # Already a member
    await pool.execute(
        "INSERT INTO room_members (room_id, user_id, role) VALUES ($1, $2, 'member')",
        room_id,
        user_id,
    )
    return True


async def leave_room(room_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    return result == "DELETE 1"


async def is_member(room_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    return row is not None


async def get_members(room_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id AS user_id, u.name, u.display_name, u.type, rm.role, rm.joined_at "
        "FROM room_members rm INNER JOIN users u ON rm.user_id = u.id "
        "WHERE rm.room_id = $1 ORDER BY rm.joined_at",
        room_id,
    )
    return [dict(r) for r in rows]


async def delete_room(room_id: UUID, user_id: UUID) -> bool:
    """Delete room. Returns True if deleted, False if not owner."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    if not row or row["role"] != "owner":
        return False
    await pool.execute("DELETE FROM rooms WHERE id = $1", room_id)
    return True


async def set_matrix_room_id(room_id: UUID, matrix_room_id: str):
    pool = get_pool()
    await pool.execute(
        "UPDATE rooms SET matrix_room_id = $1 WHERE id = $2",
        matrix_room_id,
        room_id,
    )
