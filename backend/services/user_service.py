from uuid import UUID

from ..auth import create_api_key, hash_password, verify_password
from ..database import get_pool


async def register_user(
    name: str,
    display_name: str | None,
    description: str = "",
    password: str | None = None,
) -> tuple[dict, str]:
    """Register a new user. Returns (user_row, raw_api_key)."""
    pool = get_pool()
    pw_hash = hash_password(password) if password else None
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (name, display_name, password_hash, description) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, name, display_name, description, created_at, last_seen",
            name,
            display_name or name,
            pw_hash,
            description,
        )
    except Exception as e:
        if "unique" in str(e).lower() and "name" in str(e).lower():
            raise ValueError(f"Username '{name}' is already taken")
        raise
    user = dict(row)
    api_key = await create_api_key(user["id"], name="password register")

    # Auto-provision a default workspace for new users.
    # workspaces.name is VARCHAR(128); trim the display so the suffix always fits.
    from . import workspace_service

    suffix = "'s Workspace"
    ws_name = f"{user['display_name'][: 128 - len(suffix)]}{suffix}"
    await workspace_service.create_workspace(
        name=ws_name,
        description="",
        creator_id=user["id"],
        is_public=False,
    )
    return user, api_key


async def get_user_by_id(user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, description, created_at, last_seen "
        "FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def update_user(
    user_id: UUID,
    display_name: str | None = None,
    description: str | None = None,
    password: str | None = None,
    current_password: str | None = None,
    current_key_id: UUID | None = None,
) -> dict:
    """Update profile fields. Password changes must present `current_password`,
    and revoke every other API key so a stolen session can't outlive the rotation.
    """
    pool = get_pool()

    if password is not None:
        if not current_password:
            raise ValueError("current_password is required to change password")
        existing_hash = await pool.fetchval(
            "SELECT password_hash FROM users WHERE id = $1", user_id
        )
        if not existing_hash or not verify_password(current_password, existing_hash):
            raise ValueError("Current password is incorrect")

    sets = []
    args = []
    idx = 1
    if display_name is not None:
        sets.append(f"display_name = ${idx}")
        args.append(display_name)
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        args.append(description)
        idx += 1
    if password is not None:
        sets.append(f"password_hash = ${idx}")
        args.append(hash_password(password))
        idx += 1
    if not sets:
        row = await pool.fetchrow(
            "SELECT id, name, display_name, description, created_at, last_seen "
            "FROM users WHERE id = $1",
            user_id,
        )
        return dict(row)
    args.append(user_id)
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, name, display_name, description, created_at, last_seen",
        *args,
    )

    if password is not None:
        # Revoke every other active key. The caller's key stays valid so the
        # user doesn't get kicked out of the tab that just changed the password.
        await pool.execute(
            "UPDATE user_api_keys SET revoked_at = now() "
            "WHERE user_id = $1 AND revoked_at IS NULL AND id <> $2",
            user_id,
            current_key_id,
        )
    return dict(row)


async def authenticate_by_password(name: str, password: str) -> tuple[dict, str]:
    """Authenticate by username + password. Returns (user_dict, new_api_key)."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, description, created_at, last_seen, password_hash "
        "FROM users WHERE name = $1",
        name,
    )
    if not row or not row["password_hash"]:
        raise ValueError("Invalid username or password")
    if not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid username or password")
    # Each login mints a fresh key — prior keys keep working so other devices
    # don't get logged out.
    api_key = await create_api_key(row["id"], name="password login")
    await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", row["id"])
    user = {k: v for k, v in dict(row).items() if k != "password_hash"}
    return user, api_key
