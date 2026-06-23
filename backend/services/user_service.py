from uuid import UUID

from ..auth import create_api_key, hash_api_key, hash_password, verify_password
from ..database import get_pool


async def register_user(
    name: str,
    display_name: str | None,
    description: str = "",
    password: str | None = None,
    email: str | None = None,
) -> tuple[dict, str]:
    """Register a new user. Returns (user_row, raw_api_key)."""
    pool = get_pool()
    if display_name is not None and not display_name.strip():
        raise ValueError("display_name is required")
    pw_hash = hash_password(password) if password else None
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (name, display_name, password_hash, description, email) "
            "VALUES ($1, $2, $3, $4, $5) "
            "RETURNING id, name, display_name, email, description, created_at, last_seen",
            name,
            display_name or name,
            pw_hash,
            description,
            email,
        )
    except Exception as e:
        if "unique" in str(e).lower() and "name" in str(e).lower():
            raise ValueError(f"Username '{name}' is already taken")
        raise
    user = dict(row)
    api_key = await create_api_key(user["id"], name="password register", key_type="password")

    # Seed the new user's scope (the user is their own scope).
    from . import user_scope_service

    await user_scope_service.seed_user_scope(user["id"])

    # Turn any pending share invites for this email into real shares.
    from . import share_service

    await share_service.convert_pending_invites(user["id"], email)
    return user, api_key


async def get_user_by_id(user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, email, description, created_at, last_seen, "
        "       role, referral_source, use_case "
        "FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def get_user_by_email(email: str) -> dict | None:
    """Case-insensitive lookup. Used by the Slack agent to map a Slack user's
    email to their Stash account."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, email, description, created_at, last_seen "
        "FROM users WHERE lower(email) = lower($1)",
        email,
    )
    return dict(row) if row else None


async def update_user(
    user_id: UUID,
    display_name: str | None = None,
    description: str | None = None,
    password: str | None = None,
    current_password: str | None = None,
    current_key_id: UUID | None = None,
    role: str | None = None,
    referral_source: str | None = None,
    use_case: str | None = None,
) -> dict:
    """Update profile fields. Password changes must present `current_password`,
    and revoke every other API key so a stolen session can't outlive the rotation.
    """
    pool = get_pool()
    if display_name is not None and not display_name.strip():
        raise ValueError("display_name is required")

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
    if role is not None:
        sets.append(f"role = ${idx}")
        args.append(role)
        idx += 1
    if referral_source is not None:
        sets.append(f"referral_source = ${idx}")
        args.append(referral_source)
        idx += 1
    if use_case is not None:
        sets.append(f"use_case = ${idx}")
        args.append(use_case)
        idx += 1
    if not sets:
        row = await pool.fetchrow(
            "SELECT id, name, display_name, email, description, created_at, last_seen, "
            "       role, referral_source, use_case "
            "FROM users WHERE id = $1",
            user_id,
        )
        return dict(row)
    args.append(user_id)
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, name, display_name, email, description, created_at, last_seen, "
        "          role, referral_source, use_case",
        *args,
    )

    if password is not None:
        if current_key_id is not None:
            await pool.execute(
                "UPDATE user_api_keys SET revoked_at = now() "
                "WHERE user_id = $1 AND revoked_at IS NULL AND id <> $2",
                user_id,
                current_key_id,
            )
        else:
            await pool.execute(
                "UPDATE user_api_keys SET revoked_at = now() "
                "WHERE user_id = $1 AND revoked_at IS NULL",
                user_id,
            )
    return dict(row)


async def authenticate_by_password(name: str, password: str) -> tuple[dict, str]:
    """Authenticate by username + password. Returns (user_dict, new_api_key)."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, email, description, created_at, last_seen, password_hash "
        "FROM users WHERE name = $1",
        name,
    )
    if not row or not row["password_hash"]:
        raise ValueError("Invalid username or password")
    if not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid username or password")
    # Each login mints a fresh key — prior keys keep working so other devices
    # don't get logged out.
    api_key = await create_api_key(row["id"], name="password login", key_type="password")
    await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", row["id"])
    user = {k: v for k, v in dict(row).items() if k != "password_hash"}
    return user, api_key


CLI_AUTH_TTL_INTERVAL = "10 minutes"


async def cleanup_expired_cli_auth_sessions() -> int:
    """Drop expired CLI auth sessions and revoke their unclaimed device keys.

    DELETE ... RETURNING claims each expired row exactly once, so a poll that
    concurrently claims (and deletes) the same session at the TTL boundary can
    never have its just-delivered key revoked here. Returns the revoke count.
    """
    pool = get_pool()
    expired = await pool.fetch(
        "DELETE FROM cli_auth_sessions "
        f"WHERE created_at < now() - interval '{CLI_AUTH_TTL_INTERVAL}' "
        "RETURNING api_key"
    )
    revoked = 0
    for row in expired:
        if row["api_key"] is None:
            continue
        await pool.execute(
            "UPDATE user_api_keys SET revoked_at = now() "
            "WHERE key_hash = $1 AND revoked_at IS NULL",
            hash_api_key(row["api_key"]),
        )
        revoked += 1
    return revoked
