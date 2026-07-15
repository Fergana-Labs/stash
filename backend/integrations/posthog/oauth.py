"""Stateless OAuth 2.0 flow for PostHog's hosted MCP server."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from ...config import settings
from ...database import get_pool
from ...services import security_audit_service
from ..crypto import integration_fernet

RESOURCE = "https://mcp.posthog.com"
SCOPES = "openid profile email account:read project:read dashboard:read insight:read feature_flag:read experiment:read query:read"
STATE_TTL = timedelta(minutes=10)
PROTECTED_RESOURCE_METADATA = "https://mcp.posthog.com/.well-known/oauth-protected-resource"
_metadata: dict | None = None


def _redirect_uri() -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}/api/v1/integrations/posthog/callback"


async def _discover() -> dict:
    global _metadata
    if _metadata is not None:
        return _metadata
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resource = (await client.get(PROTECTED_RESOURCE_METADATA)).raise_for_status().json()
        issuer = resource["authorization_servers"][0].rstrip("/")
        server = (
            (await client.get(f"{issuer}/.well-known/oauth-authorization-server"))
            .raise_for_status()
            .json()
        )
    _metadata = {
        "authorization_endpoint": server["authorization_endpoint"],
        "token_endpoint": server["token_endpoint"],
        "registration_endpoint": server["registration_endpoint"],
        "revocation_endpoint": server["revocation_endpoint"],
        "userinfo_endpoint": server["userinfo_endpoint"],
    }
    return _metadata


async def _register_client() -> dict:
    meta = await _discover()
    body = {
        "client_name": "Stash",
        "redirect_uris": [_redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPES,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        return (
            (await client.post(meta["registration_endpoint"], json=body)).raise_for_status().json()
        )


def _encode_state(user_id: UUID, return_to: str | None, verifier: str, client: dict) -> str:
    payload = {
        "u": str(user_id),
        "r": return_to,
        "v": verifier,
        "c": client,
        "t": datetime.now(UTC).isoformat(),
    }
    return integration_fernet().encrypt(json.dumps(payload).encode()).decode()


def _decode_state(state: str) -> dict:
    try:
        raw = integration_fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    return json.loads(raw)


async def _post_token(data: dict) -> dict:
    meta = await _discover()
    async with httpx.AsyncClient(timeout=15.0) as client:
        return (await client.post(meta["token_endpoint"], data=data)).raise_for_status().json()


def _expires_at(token: dict) -> datetime | None:
    if "expires_in" not in token:
        return None
    return datetime.now(UTC) + timedelta(seconds=int(token["expires_in"]))


async def start_authorization(user_id: UUID, return_to: str | None) -> str:
    meta = await _discover()
    client = await _register_client()
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    state = _encode_state(user_id, return_to, verifier, client)
    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": _redirect_uri(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    }
    return f"{meta['authorization_endpoint']}?{httpx.QueryParams(params)}"


async def finish_authorization(code: str, state: str) -> str | None:
    payload = _decode_state(state)
    client = payload["c"]
    token = await _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": client["client_id"],
            "code_verifier": payload["v"],
            "resource": RESOURCE,
        }
    )
    account = await _fetch_account(token["access_token"])
    user_id = UUID(payload["u"])
    await _store_connection(user_id, token, client, account)
    await security_audit_service.record_user_event(
        action="integration.connected",
        actor_user_id=user_id,
        target_type="integration",
        target_id="posthog",
        provider="posthog",
        metadata={"auth_kind": "mcp_oauth"},
    )
    return payload["r"]


async def _fetch_account(access_token: str) -> dict:
    meta = await _discover()
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        info = (await client.get(meta["userinfo_endpoint"])).raise_for_status().json()
    email = info.get("email")
    return {"email": email, "display_name": info.get("name") or email or "PostHog"}


async def _store_connection(user_id: UUID, token: dict, client: dict, account: dict) -> None:
    f = integration_fernet()
    await get_pool().execute(
        """
        INSERT INTO user_integrations (
            user_id, provider, account_key, access_token_encrypted, refresh_token_encrypted,
            scopes, expires_at, account_email, account_display_name, client_info, updated_at
        ) VALUES ($1, 'posthog', 'default', $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (user_id, provider, account_key) DO UPDATE SET
            access_token_encrypted = EXCLUDED.access_token_encrypted,
            refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
            scopes = EXCLUDED.scopes, expires_at = EXCLUDED.expires_at,
            account_email = EXCLUDED.account_email,
            account_display_name = EXCLUDED.account_display_name,
            client_info = EXCLUDED.client_info, updated_at = now()
        """,
        user_id,
        f.encrypt(token["access_token"].encode()),
        f.encrypt(token["refresh_token"].encode()) if token.get("refresh_token") else None,
        (token.get("scope") or SCOPES).split(),
        _expires_at(token),
        account["email"],
        account["display_name"],
        json.dumps(client),
    )


async def get_valid_access_token(user_id: UUID) -> str:
    row = await get_pool().fetchrow(
        """SELECT access_token_encrypted, refresh_token_encrypted, expires_at, client_info
           FROM user_integrations
           WHERE user_id = $1 AND provider = 'posthog' AND account_key = 'default'""",
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=401, detail="not connected to posthog")
    f = integration_fernet()
    if row["expires_at"] is None or row["expires_at"] > datetime.now(UTC) + timedelta(seconds=60):
        return f.decrypt(bytes(row["access_token_encrypted"])).decode()
    if row["refresh_token_encrypted"] is None:
        raise HTTPException(status_code=401, detail="posthog token expired; reconnect required")
    refresh_token = f.decrypt(bytes(row["refresh_token_encrypted"])).decode()
    client = json.loads(row["client_info"])
    token = await _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client["client_id"],
            "resource": RESOURCE,
        }
    )
    await get_pool().execute(
        """UPDATE user_integrations SET access_token_encrypted = $2,
           refresh_token_encrypted = COALESCE($3, refresh_token_encrypted), expires_at = $4,
           updated_at = now() WHERE user_id = $1 AND provider = 'posthog' AND account_key = 'default'""",
        user_id,
        f.encrypt(token["access_token"].encode()),
        f.encrypt(token["refresh_token"].encode()) if token.get("refresh_token") else None,
        _expires_at(token),
    )
    return token["access_token"]


async def revoke(access_token: str) -> None:
    meta = await _discover()
    async with httpx.AsyncClient(timeout=15.0) as client:
        (
            await client.post(meta["revocation_endpoint"], data={"token": access_token})
        ).raise_for_status()
