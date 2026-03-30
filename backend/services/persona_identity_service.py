from uuid import UUID

from ..auth import generate_api_key, hash_api_key
from ..database import get_pool

MAX_PERSONAS_PER_OWNER = 50


async def create_persona(
    owner_id: UUID,
    name: str,
    display_name: str | None,
    description: str,
) -> tuple[dict, str]:
    """Create a persona identity owned by a human user. Returns (persona_row, raw_api_key).

    Auto-provisions a personal notebook and history store for the persona.
    """
    pool = get_pool()

    # Validate owner is human
    owner = await pool.fetchrow("SELECT type FROM users WHERE id = $1", owner_id)
    if not owner or owner["type"] != "human":
        raise ValueError("Only human users can create persona identities")

    # Rate limit
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE owner_id = $1", owner_id
    )
    if count >= MAX_PERSONAS_PER_OWNER:
        raise ValueError(f"Maximum of {MAX_PERSONAS_PER_OWNER} personas per user")

    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Create the persona user
            try:
                row = await conn.fetchrow(
                    "INSERT INTO users (name, display_name, type, api_key_hash, description, owner_id) "
                    "VALUES ($1, $2, 'persona', $3, $4, $5) "
                    "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
                    name,
                    display_name or name,
                    key_hash,
                    description,
                    owner_id,
                )
            except Exception as e:
                if "unique" in str(e).lower() and "name" in str(e).lower():
                    raise ValueError(f"Persona name '{name}' is already taken")
                raise

            persona_id = row["id"]

            # Auto-provision personal notebook
            nb_row = await conn.fetchrow(
                "INSERT INTO notebooks (workspace_id, name, description, created_by) "
                "VALUES (NULL, $1, $2, $3) RETURNING id",
                name, f"Notebook for persona {name}", persona_id,
            )

            # Auto-provision personal history store
            hist_row = await conn.fetchrow(
                "INSERT INTO histories (workspace_id, name, description, created_by) "
                "VALUES (NULL, $1, $2, $3) RETURNING id",
                name, f"History for persona {name}", persona_id,
            )

            # Link resources to persona
            await conn.execute(
                "UPDATE users SET notebook_id = $1, history_id = $2 WHERE id = $3",
                nb_row["id"], hist_row["id"], persona_id,
            )

    persona = dict(row)
    persona["notebook_id"] = nb_row["id"]
    persona["history_id"] = hist_row["id"]
    return persona, api_key


async def list_owner_personas(owner_id: UUID) -> list[dict]:
    """List all personas owned by a user."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, name, display_name, type, description, owner_id, "
        "notebook_id, history_id, created_at, last_seen "
        "FROM users WHERE owner_id = $1 ORDER BY created_at",
        owner_id,
    )
    return [dict(r) for r in rows]


async def get_persona(persona_id: UUID, owner_id: UUID) -> dict | None:
    """Get a specific persona. Validates ownership."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, display_name, type, description, owner_id, "
        "notebook_id, history_id, created_at, last_seen "
        "FROM users WHERE id = $1 AND owner_id = $2",
        persona_id,
        owner_id,
    )
    return dict(row) if row else None


async def update_persona(
    persona_id: UUID,
    owner_id: UUID,
    display_name: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update persona details. Owner only."""
    pool = get_pool()
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
    if not sets:
        return await get_persona(persona_id, owner_id)
    args.extend([persona_id, owner_id])
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE id = ${idx} AND owner_id = ${idx + 1} "
        "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
        *args,
    )
    return dict(row) if row else None


async def rotate_persona_key(persona_id: UUID, owner_id: UUID) -> tuple[dict, str] | None:
    """Generate a new API key for a persona. Returns (persona_row, new_api_key) or None."""
    pool = get_pool()
    # Verify ownership
    existing = await pool.fetchrow(
        "SELECT id FROM users WHERE id = $1 AND owner_id = $2", persona_id, owner_id
    )
    if not existing:
        return None
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    row = await pool.fetchrow(
        "UPDATE users SET api_key_hash = $1 WHERE id = $2 "
        "RETURNING id, name, display_name, type, description, owner_id, notebook_id, history_id, created_at, last_seen",
        key_hash,
        persona_id,
    )
    return dict(row), api_key


async def delete_persona(persona_id: UUID, owner_id: UUID) -> bool:
    """Delete a persona identity and its provisioned resources. Returns True if deleted."""
    pool = get_pool()

    # Fetch resource IDs before deleting
    persona = await pool.fetchrow(
        "SELECT notebook_id, history_id FROM users WHERE id = $1 AND owner_id = $2",
        persona_id, owner_id,
    )
    if not persona:
        return False

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Delete persona user (cascades to workspace_members etc.)
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1 AND owner_id = $2", persona_id, owner_id,
            )
            if result != "DELETE 1":
                return False
            # Clean up provisioned resources
            if persona["notebook_id"]:
                await conn.execute("DELETE FROM notebooks WHERE id = $1", persona["notebook_id"])
            if persona["history_id"]:
                await conn.execute("DELETE FROM histories WHERE id = $1", persona["history_id"])

    return True


async def get_persona_resources(persona_id: UUID) -> dict | None:
    """Get the notebook_id and history_id for a persona."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT notebook_id, history_id FROM users WHERE id = $1 AND type = 'persona'",
        persona_id,
    )
    return dict(row) if row else None


async def provision_existing_persona(persona_id: UUID) -> dict | None:
    """Provision notebook + history for an existing persona that doesn't have them yet."""
    pool = get_pool()

    persona = await pool.fetchrow(
        "SELECT id, name, notebook_id, history_id FROM users WHERE id = $1 AND type = 'persona'",
        persona_id,
    )
    if not persona:
        return None

    async with pool.acquire() as conn:
        async with conn.transaction():
            notebook_id = persona["notebook_id"]
            history_id = persona["history_id"]

            if not notebook_id:
                nb_row = await conn.fetchrow(
                    "INSERT INTO notebooks (workspace_id, name, description, created_by) "
                    "VALUES (NULL, $1, $2, $3) RETURNING id",
                    persona["name"], f"Notebook for persona {persona['name']}", persona_id,
                )
                notebook_id = nb_row["id"]

            if not history_id:
                hist_row = await conn.fetchrow(
                    "INSERT INTO histories (workspace_id, name, description, created_by) "
                    "VALUES (NULL, $1, $2, $3) RETURNING id",
                    persona["name"], f"History for persona {persona['name']}", persona_id,
                )
                history_id = hist_row["id"]

            await conn.execute(
                "UPDATE users SET notebook_id = $1, history_id = $2 WHERE id = $3",
                notebook_id, history_id, persona_id,
            )

    return {"notebook_id": notebook_id, "history_id": history_id}
