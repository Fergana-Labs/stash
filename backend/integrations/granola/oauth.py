"""Granola OAuth 2.0 (MCP server) — stateless, manual flow.

Granola's MCP server (`mcp.granola.ai`) authenticates with standard OAuth 2.0:
Protected-Resource-Metadata discovery → Authorization-Server-Metadata discovery
→ Dynamic Client Registration (RFC 7591, public client) → authorization code +
PKCE → token. There is no pre-shared client_id/secret, so we register a fresh
client per connect and carry that registration (plus the PKCE verifier) through
the encrypted `state` blob from /connect to /callback. Nothing is held in
process between the two requests — the flow is fully stateless and so is safe
under multiple workers.

We drive these five plain HTTP calls ourselves rather than going through the
`mcp` SDK's OAuthClientProvider: that class runs the handshake inline off an
open MCP session (driven by redirect/callback handlers), which doesn't map onto
a two-request web redirect and can't refresh head-lessly in a worker. The SDK is
still used as the MCP transport for tool calls (see client.py).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from ...config import settings
from ...database import get_pool

# Canonical resource for RFC 8707 — the token is bound to this MCP server.
RESOURCE = "https://mcp.granola.ai/mcp"
SCOPES = "openid email profile offline_access"
CLIENT_NAME = "Stash"

# How long the user has between /connect and finishing sign-in at Granola.
STATE_TTL = timedelta(minutes=10)

# The auth-server endpoints are static; discover once per process.
_metadata: dict | None = None


def _fernet() -> Fernet:
    if not settings.INTEGRATIONS_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="INTEGRATIONS_ENCRYPTION_KEY is not set")
    return Fernet(settings.INTEGRATIONS_ENCRYPTION_KEY.encode())


def _redirect_uri() -> str:
    if not settings.GRANOLA_OAUTH_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="GRANOLA_OAUTH_REDIRECT_URI is not set")
    return settings.GRANOLA_OAUTH_REDIRECT_URI


# --- OAuth metadata discovery ---------------------------------------------


async def _discover() -> dict:
    """Resolve the authorization-server endpoints from the MCP server.

    PRM (on the resource) names the auth server; ASM (on the auth server) names
    the authorize/token/register endpoints.
    """
    global _metadata
    if _metadata is not None:
        return _metadata

    parsed = urlparse(settings.GRANOLA_MCP_URL)
    base = f"{parsed.scheme}://{parsed.netloc}"
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        prm = (
            (await client.get(f"{base}/.well-known/oauth-protected-resource"))
            .raise_for_status()
            .json()
        )
        auth_server = prm["authorization_servers"][0].rstrip("/")
        asm = (
            (await client.get(f"{auth_server}/.well-known/oauth-authorization-server"))
            .raise_for_status()
            .json()
        )

    _metadata = {
        "authorization_endpoint": asm["authorization_endpoint"],
        "token_endpoint": asm["token_endpoint"],
        "registration_endpoint": asm["registration_endpoint"],
    }
    return _metadata


async def _register_client() -> dict:
    """Dynamic Client Registration — returns the RFC 7591 client (public, PKCE)."""
    meta = await _discover()
    body = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [_redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPES,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(meta["registration_endpoint"], json=body)
        resp.raise_for_status()
        return resp.json()


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


# --- State blob (carries the per-connect secrets to the callback) ----------


def _encode_state(user_id: UUID, return_to: str | None, code_verifier: str, client: dict) -> str:
    payload = {
        "u": str(user_id),
        "r": return_to,
        "v": code_verifier,
        "c": client,
        "t": datetime.now(UTC).isoformat(),
    }
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def _decode_state(state: str) -> dict:
    try:
        raw = _fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    return json.loads(raw)


# --- Token requests --------------------------------------------------------


async def _post_token(data: dict) -> dict:
    meta = await _discover()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
        resp.raise_for_status()
        return resp.json()


def _expires_at(token: dict) -> datetime | None:
    expires_in = token.get("expires_in")
    if not expires_in:
        return None
    return datetime.now(UTC) + timedelta(seconds=int(expires_in))


# --- Public flow used by the router ----------------------------------------


async def start_authorization(user_id: UUID, return_to: str | None) -> str:
    """Register a client, build the PKCE authorize URL, and return it."""
    meta = await _discover()
    client = await _register_client()
    verifier, challenge = _pkce()
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


async def finish_authorization(code: str, state: str) -> str:
    """Exchange the code for tokens, store the connection, return where to land."""
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
    await _store_connection(UUID(payload["u"]), token, client, account)
    return payload["r"]


async def _fetch_account(access_token: str) -> dict:
    """Resolve the connected account for display via the MCP get_account_info tool."""
    from .client import call_tool_json, granola_session

    async with granola_session(access_token) as session:
        info = await call_tool_json(session, "get_account_info") or {}
    email = info.get("email")
    display = info.get("workspace_name") or info.get("name") or email or "Granola"
    return {"email": email, "display_name": display}


# --- Storage (user_integrations, incl. the DCR client_info) ----------------


async def _store_connection(user_id: UUID, token: dict, client: dict, account: dict) -> None:
    f = _fernet()
    pool = get_pool()
    scopes = (token.get("scope") or SCOPES).split()
    await pool.execute(
        """
        INSERT INTO user_integrations (
            user_id, provider, access_token_encrypted, refresh_token_encrypted,
            scopes, expires_at, account_email, account_display_name,
            client_info, updated_at
        )
        VALUES ($1, 'granola', $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (user_id, provider) DO UPDATE SET
            access_token_encrypted = EXCLUDED.access_token_encrypted,
            refresh_token_encrypted = COALESCE(EXCLUDED.refresh_token_encrypted, user_integrations.refresh_token_encrypted),
            scopes = EXCLUDED.scopes,
            expires_at = EXCLUDED.expires_at,
            account_email = EXCLUDED.account_email,
            account_display_name = EXCLUDED.account_display_name,
            client_info = EXCLUDED.client_info,
            updated_at = now()
        """,
        user_id,
        f.encrypt(token["access_token"].encode()),
        f.encrypt(token["refresh_token"].encode()) if token.get("refresh_token") else None,
        scopes,
        _expires_at(token),
        account.get("email"),
        account.get("display_name"),
        json.dumps(client),
    )


async def get_valid_access_token(user_id: UUID) -> str:
    """Return a usable access token, refreshing via the stored refresh token if
    it has expired. Used by the indexer, which runs without an interactive flow."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT access_token_encrypted, refresh_token_encrypted, expires_at, client_info
        FROM user_integrations WHERE user_id = $1 AND provider = 'granola'
        """,
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=401, detail="not connected to granola")

    f = _fernet()
    expires_at = row["expires_at"]
    fresh = expires_at is None or expires_at > datetime.now(UTC) + timedelta(seconds=60)
    if fresh:
        return f.decrypt(bytes(row["access_token_encrypted"])).decode()

    refresh_token = (
        f.decrypt(bytes(row["refresh_token_encrypted"])).decode()
        if row["refresh_token_encrypted"]
        else None
    )
    if not refresh_token:
        raise HTTPException(status_code=401, detail="granola token expired; reconnect required")

    client = json.loads(row["client_info"])
    token = await _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client["client_id"],
            "resource": RESOURCE,
        }
    )
    await pool.execute(
        """
        UPDATE user_integrations SET
            access_token_encrypted = $2,
            refresh_token_encrypted = COALESCE($3, refresh_token_encrypted),
            expires_at = $4,
            updated_at = now()
        WHERE user_id = $1 AND provider = 'granola'
        """,
        user_id,
        f.encrypt(token["access_token"].encode()),
        f.encrypt(token["refresh_token"].encode()) if token.get("refresh_token") else None,
        _expires_at(token),
    )
    return token["access_token"]
