"""Token storage for user_integrations.

All access/refresh tokens are encrypted at rest with Fernet. The keyring comes
from `INTEGRATIONS_ENCRYPTION_KEY`: the first comma-separated key encrypts new
tokens, and any later keys can decrypt rows during a planned rotation. Providers
never touch the DB; they only return TokenSet/AccountInfo from their methods.

Refresh-on-use: `get_valid_token` checks `expires_at` and refreshes if
the token expires in less than 60s, writing the new token back before
returning it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException

from ..database import get_pool
from .base import AccountInfo, TokenSet
from .crypto import integration_fernet
from .registry import get_provider


def _encrypt(plaintext: str | None) -> bytes | None:
    if plaintext is None:
        return None
    return integration_fernet().encrypt(plaintext.encode())


def _decrypt(ciphertext: bytes | None) -> str | None:
    if ciphertext is None:
        return None
    return integration_fernet().decrypt(bytes(ciphertext)).decode()


async def store_token(
    user_id: UUID,
    provider: str,
    token: TokenSet,
    account: AccountInfo,
) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO user_integrations (
            user_id, provider,
            access_token_encrypted, refresh_token_encrypted,
            scopes, expires_at,
            account_email, account_display_name,
            updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (user_id, provider) DO UPDATE SET
            access_token_encrypted = EXCLUDED.access_token_encrypted,
            refresh_token_encrypted = COALESCE(EXCLUDED.refresh_token_encrypted, user_integrations.refresh_token_encrypted),
            scopes = EXCLUDED.scopes,
            expires_at = EXCLUDED.expires_at,
            account_email = EXCLUDED.account_email,
            account_display_name = EXCLUDED.account_display_name,
            updated_at = now()
        """,
        user_id,
        provider,
        _encrypt(token.access_token),
        _encrypt(token.refresh_token),
        token.scopes,
        token.expires_at,
        account.email,
        account.display_name,
    )


async def get_valid_token(user_id: UUID, provider: str) -> str:
    """Return a usable access token, refreshing if expired."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT access_token_encrypted, refresh_token_encrypted, expires_at, scopes
        FROM user_integrations WHERE user_id = $1 AND provider = $2
        """,
        user_id,
        provider,
    )
    if row is None:
        raise HTTPException(
            status_code=401,
            detail=f"not connected to {provider}",
        )

    expires_at = row["expires_at"]
    needs_refresh = expires_at is not None and expires_at < datetime.now(UTC) + timedelta(
        seconds=60
    )
    if not needs_refresh:
        return _decrypt(row["access_token_encrypted"])  # type: ignore[return-value]

    refresh_token = _decrypt(row["refresh_token_encrypted"])
    if not refresh_token:
        # Expired but no refresh token — user must reconnect.
        raise HTTPException(
            status_code=401,
            detail=f"{provider} token expired; reconnect required",
        )

    provider_impl = get_provider(provider)
    new_token = await provider_impl.refresh(refresh_token)
    await pool.execute(
        """
        UPDATE user_integrations SET
            access_token_encrypted = $3,
            refresh_token_encrypted = COALESCE($4, refresh_token_encrypted),
            expires_at = $5,
            updated_at = now()
        WHERE user_id = $1 AND provider = $2
        """,
        user_id,
        provider,
        _encrypt(new_token.access_token),
        _encrypt(new_token.refresh_token),
        new_token.expires_at,
    )
    return new_token.access_token


async def revoke_stored(user_id: UUID, provider: str) -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT access_token_encrypted FROM user_integrations "
        "WHERE user_id = $1 AND provider = $2",
        user_id,
        provider,
    )
    if row is None:
        return
    access_token = _decrypt(row["access_token_encrypted"])
    provider_impl = get_provider(provider)
    if access_token:
        try:
            await provider_impl.revoke(access_token)
        except Exception:
            # Provider may already consider the token invalid; we still
            # delete our local copy so the user can reconnect cleanly.
            pass
    await pool.execute(
        "DELETE FROM user_integrations WHERE user_id = $1 AND provider = $2",
        user_id,
        provider,
    )


async def status(user_id: UUID, provider: str) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT scopes, expires_at, account_email, account_display_name, created_at
        FROM user_integrations WHERE user_id = $1 AND provider = $2
        """,
        user_id,
        provider,
    )
    if row is None:
        return {"connected": False}
    return {
        "connected": True,
        "scopes": list(row["scopes"] or []),
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "account_email": row["account_email"],
        "account_display_name": row["account_display_name"],
        "connected_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def list_connections(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT provider, scopes, expires_at, account_email, account_display_name, created_at
        FROM user_integrations WHERE user_id = $1
        ORDER BY provider
        """,
        user_id,
    )
    return [
        {
            "provider": r["provider"],
            "scopes": list(r["scopes"] or []),
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "account_email": r["account_email"],
            "account_display_name": r["account_display_name"],
            "connected_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
