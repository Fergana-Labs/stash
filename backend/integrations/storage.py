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

DEFAULT_ACCOUNT_KEY = "default"


def _encrypt(plaintext: str | None) -> bytes | None:
    if plaintext is None:
        return None
    return integration_fernet().encrypt(plaintext.encode())


def _decrypt(ciphertext: bytes | None) -> str | None:
    if ciphertext is None:
        return None
    return integration_fernet().decrypt(bytes(ciphertext)).decode()


def _account_key_for(provider: str, account: AccountInfo) -> str:
    if provider == "gmail":
        if not account.email:
            raise ValueError("Gmail account email is required")
        return account.email.strip().lower()
    return DEFAULT_ACCOUNT_KEY


def _account_row(row) -> dict:
    return {
        "account_key": row["account_key"],
        "account_email": row["account_email"],
        "account_display_name": row["account_display_name"],
        "scopes": list(row["scopes"] or []),
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "connected_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def store_token(
    user_id: UUID,
    provider: str,
    token: TokenSet,
    account: AccountInfo,
) -> None:
    pool = get_pool()
    account_key = _account_key_for(provider, account)
    await pool.execute(
        """
        INSERT INTO user_integrations (
            user_id, provider, account_key,
            access_token_encrypted, refresh_token_encrypted,
            scopes, expires_at,
            account_email, account_display_name,
            updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
        ON CONFLICT (user_id, provider, account_key) DO UPDATE SET
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
        account_key,
        _encrypt(token.access_token),
        _encrypt(token.refresh_token),
        token.scopes,
        token.expires_at,
        account.email,
        account.display_name,
    )


_TOKEN_QUERY = """
    SELECT access_token_encrypted, refresh_token_encrypted, expires_at
    FROM user_integrations
    WHERE user_id = $1 AND provider = $2 AND account_key = $3
"""


def _needs_refresh(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at < datetime.now(UTC) + timedelta(seconds=60)


async def get_valid_token(
    user_id: UUID,
    provider: str,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> str:
    """Return a usable access token, refreshing if expired."""
    pool = get_pool()
    row = await pool.fetchrow(_TOKEN_QUERY, user_id, provider, account_key)
    if row is None:
        raise HTTPException(
            status_code=401,
            detail=f"not connected to {provider}",
        )
    if not _needs_refresh(row["expires_at"]):
        return _decrypt(row["access_token_encrypted"])  # type: ignore[return-value]

    # Refresh under an advisory lock. Some providers (X) rotate refresh tokens
    # single-use, so two concurrent refreshes invalidate each other's tokens
    # and can kill the connection. Concurrent callers queue on the lock, then
    # the re-read sees the winner's fresh token and returns it without a
    # second provider call.
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"user_integrations:{user_id}:{provider}:{account_key}",
        )
        row = await conn.fetchrow(_TOKEN_QUERY, user_id, provider, account_key)
        if row is None:
            raise HTTPException(
                status_code=401,
                detail=f"not connected to {provider}",
            )
        if not _needs_refresh(row["expires_at"]):
            return _decrypt(row["access_token_encrypted"])  # type: ignore[return-value]

        refresh_token = _decrypt(row["refresh_token_encrypted"])
        if not refresh_token:
            # Expired but no refresh token — user must reconnect.
            raise HTTPException(
                status_code=401,
                detail=f"{provider} token expired; reconnect required",
            )

        new_token = await get_provider(provider).refresh(refresh_token)
        await conn.execute(
            """
            UPDATE user_integrations SET
                access_token_encrypted = $3,
                refresh_token_encrypted = COALESCE($4, refresh_token_encrypted),
                expires_at = $5,
                updated_at = now()
            WHERE user_id = $1 AND provider = $2
              AND account_key = $6
            """,
            user_id,
            provider,
            _encrypt(new_token.access_token),
            _encrypt(new_token.refresh_token),
            new_token.expires_at,
            account_key,
        )
        return new_token.access_token


async def revoke_stored(
    user_id: UUID,
    provider: str,
    account_key: str | None = None,
) -> None:
    pool = get_pool()
    rows = await pool.fetch(
        "DELETE FROM user_integrations WHERE user_id = $1 AND provider = $2 "
        "AND ($3::text IS NULL OR account_key = $3) "
        "RETURNING access_token_encrypted",
        user_id,
        provider,
        account_key,
    )
    if not rows:
        return
    provider_impl = get_provider(provider)
    for row in rows:
        try:
            access_token = _decrypt(row["access_token_encrypted"])
            if access_token:
                await provider_impl.revoke(access_token)
        except Exception:
            # Disconnect must always remove Stash's local credential rows.
            # Provider revocation is best effort because tokens may already be
            # invalid or undecryptable after key rotation mistakes.
            pass


async def status(user_id: UUID, provider: str) -> dict:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT account_key, scopes, expires_at, account_email, account_display_name, created_at
        FROM user_integrations WHERE user_id = $1 AND provider = $2
        ORDER BY account_email NULLS LAST, account_display_name NULLS LAST, account_key
        """,
        user_id,
        provider,
    )
    if not rows:
        return {"connected": False, "accounts": []}
    accounts = [_account_row(row) for row in rows]
    first = accounts[0]
    return {
        "connected": True,
        "scopes": first["scopes"],
        "expires_at": first["expires_at"],
        "account_email": first["account_email"],
        "account_display_name": first["account_display_name"],
        "connected_at": first["connected_at"],
        "accounts": accounts,
    }


async def list_connections(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT provider, account_key, scopes, expires_at,
               account_email, account_display_name, created_at
        FROM user_integrations WHERE user_id = $1
        ORDER BY provider, account_email NULLS LAST, account_display_name NULLS LAST, account_key
        """,
        user_id,
    )
    connections: dict[str, dict] = {}
    for row in rows:
        provider = row["provider"]
        account = _account_row(row)
        if provider not in connections:
            connections[provider] = {
                "provider": provider,
                "scopes": account["scopes"],
                "expires_at": account["expires_at"],
                "account_email": account["account_email"],
                "account_display_name": account["account_display_name"],
                "connected_at": account["connected_at"],
                "accounts": [],
            }
        connections[provider]["accounts"].append(account)
    return list(connections.values())
