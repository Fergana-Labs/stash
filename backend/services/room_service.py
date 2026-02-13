import secrets
from uuid import UUID

from ..database import get_pool


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(6)[:8]


async def create_room(
    name: str, description: str, creator_id: UUID, is_public: bool = True, type: str = "chat"
) -> dict:
    pool = get_pool()
    invite_code = _generate_invite_code()
    # Retry if invite code collision (unlikely)
    for _ in range(5):
        try:
            row = await pool.fetchrow(
                "INSERT INTO rooms (name, description, creator_id, invite_code, is_public, type) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "RETURNING id, name, description, creator_id, invite_code, is_public, type, created_at",
                name,
                description,
                creator_id,
                invite_code,
                is_public,
                type,
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


async def join_room(room_id: UUID, user_id: UUID, user_name: str | None = None) -> bool:
    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT 1 FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    if existing:
        return False  # Already a member

    # Access check (creator always bypasses)
    if user_name:
        room = await get_room(room_id)
        if room and room["creator_id"] != user_id:
            allowed, reason = await check_access(room_id, user_name)
            if not allowed:
                raise ValueError(reason)

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


async def get_member_role(room_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        user_id,
    )
    return row["role"] if row else None


async def kick_member(room_id: UUID, requester_id: UUID, target_user_id: UUID) -> bool:
    """Kick a member from a room. Requester must be owner. Returns True if kicked."""
    if requester_id == target_user_id:
        raise ValueError("Cannot kick yourself — use leave instead")

    requester_role = await get_member_role(room_id, requester_id)
    if requester_role != "owner":
        raise PermissionError("Only the room owner can kick members")

    target_role = await get_member_role(room_id, target_user_id)
    if target_role is None:
        raise ValueError("User is not a member of this room")
    if target_role == "owner":
        raise ValueError("Cannot kick the room owner")

    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM room_members WHERE room_id = $1 AND user_id = $2",
        room_id,
        target_user_id,
    )
    return result == "DELETE 1"


async def update_room(
    room_id: UUID,
    requester_id: UUID,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Update room name/description. Only owner can update."""
    requester_role = await get_member_role(room_id, requester_id)
    if requester_role != "owner":
        raise PermissionError("Only the room owner can update the room")

    pool = get_pool()
    sets = []
    args = []
    idx = 1
    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        args.append(description)
        idx += 1
    if not sets:
        room = await get_room(room_id)
        return room
    args.append(room_id)
    row = await pool.fetchrow(
        f"UPDATE rooms SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, name, description, creator_id, invite_code, is_public, type, created_at",
        *args,
    )
    result = dict(row)
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM room_members WHERE room_id = $1", room_id
    )
    result["member_count"] = count
    return result


async def add_to_access_list(
    room_id: UUID, requester_id: UUID, user_name: str, list_type: str
) -> bool:
    """Add a username to a room's allow/block list. Owner only. Returns True if added."""
    requester_role = await get_member_role(room_id, requester_id)
    if requester_role != "owner":
        raise PermissionError("Only the room owner can manage access lists")

    pool = get_pool()
    try:
        await pool.execute(
            "INSERT INTO room_access_list (room_id, user_name, list_type, added_by) "
            "VALUES ($1, $2, $3, $4)",
            room_id,
            user_name,
            list_type,
            requester_id,
        )
        return True
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return False  # Already on the list
        raise


async def remove_from_access_list(
    room_id: UUID, requester_id: UUID, user_name: str, list_type: str
) -> bool:
    """Remove a username from a room's allow/block list. Owner only."""
    requester_role = await get_member_role(room_id, requester_id)
    if requester_role != "owner":
        raise PermissionError("Only the room owner can manage access lists")

    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM room_access_list WHERE room_id = $1 AND user_name = $2 AND list_type = $3",
        room_id,
        user_name,
        list_type,
    )
    return result == "DELETE 1"


async def get_access_list(room_id: UUID, list_type: str) -> list[dict]:
    """Get entries for a room's allow or block list."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT user_name, added_by, created_at FROM room_access_list "
        "WHERE room_id = $1 AND list_type = $2 ORDER BY created_at",
        room_id,
        list_type,
    )
    return [dict(r) for r in rows]


async def check_access(room_id: UUID, user_name: str) -> tuple[bool, str]:
    """Check if a user can join a room. Returns (allowed, reason)."""
    pool = get_pool()

    # Blocklist always checked first
    blocked = await pool.fetchrow(
        "SELECT 1 FROM room_access_list WHERE room_id = $1 AND user_name = $2 AND list_type = 'block'",
        room_id,
        user_name,
    )
    if blocked:
        return False, f"User '{user_name}' is blocked from this room"

    # Check if allowlist is active (any allow entries exist)
    allow_count = await pool.fetchval(
        "SELECT COUNT(*) FROM room_access_list WHERE room_id = $1 AND list_type = 'allow'",
        room_id,
    )
    if allow_count > 0:
        # Allowlist is active — user must be on it
        on_allow = await pool.fetchrow(
            "SELECT 1 FROM room_access_list WHERE room_id = $1 AND user_name = $2 AND list_type = 'allow'",
            room_id,
            user_name,
        )
        if not on_allow:
            return False, f"User '{user_name}' is not on the allow list for this room"

    return True, ""


