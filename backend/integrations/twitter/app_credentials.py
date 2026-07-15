"""Per-user X developer-app OAuth credentials (bring-your-own-app).

Stored so a user can run X OAuth against their own paid app, making
bookmark reads count against their quota instead of Stash's shared app.
The client id is not secret; the client secret is Fernet-encrypted.
"""

from uuid import UUID

from ...database import get_pool
from ..crypto import integration_fernet


async def store(owner_user_id: UUID, client_id: str, client_secret: str | None) -> None:
    secret = integration_fernet().encrypt(client_secret.encode()) if client_secret else None
    await get_pool().execute(
        """
        INSERT INTO twitter_app_credentials (owner_user_id, client_id, client_secret_encrypted)
        VALUES ($1, $2, $3)
        ON CONFLICT (owner_user_id) DO UPDATE SET
            client_id = EXCLUDED.client_id,
            client_secret_encrypted = EXCLUDED.client_secret_encrypted,
            updated_at = now()
        """,
        owner_user_id,
        client_id,
        secret,
    )


async def get(owner_user_id: UUID) -> dict | None:
    """Return {"client_id", "client_secret"} or None. The secret is decrypted."""
    row = await get_pool().fetchrow(
        "SELECT client_id, client_secret_encrypted FROM twitter_app_credentials "
        "WHERE owner_user_id = $1",
        owner_user_id,
    )
    if row is None:
        return None
    secret = (
        integration_fernet().decrypt(row["client_secret_encrypted"]).decode()
        if row["client_secret_encrypted"]
        else None
    )
    return {"client_id": row["client_id"], "client_secret": secret}


async def delete(owner_user_id: UUID) -> None:
    await get_pool().execute(
        "DELETE FROM twitter_app_credentials WHERE owner_user_id = $1", owner_user_id
    )
