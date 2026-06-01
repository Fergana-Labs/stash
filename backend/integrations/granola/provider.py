"""Granola OAuth provider.

Granola's public API (https://public-api.granola.ai/v1) is gated to Business/
Enterprise workspaces and authenticates via WorkOS OAuth 2.0 with refresh-token
rotation: each refresh returns a short-lived access token (~1h) AND a new refresh
token, invalidating the old one. Our token storage already persists a rotated
refresh token (it COALESCEs the new value), so `supports_refresh = True` is safe.

NOTE: the exact authorize/token/account endpoints below must be confirmed against
docs.granola.ai before enabling in production. The provider is inert until the
GRANOLA_OAUTH_* env vars are set (the client-id accessor raises otherwise).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

# TODO(verify against docs.granola.ai): WorkOS-backed OAuth endpoints.
AUTHORIZE_URL = "https://api.granola.ai/oauth/authorize"
TOKEN_URL = "https://api.granola.ai/oauth/token"
API_BASE = "https://public-api.granola.ai/v1"
ACCOUNT_URL = f"{API_BASE}/me"


class GranolaIntegration(Integration):
    name = "granola"
    display_name = "Granola"
    scopes = ["notes:read"]
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.GRANOLA_OAUTH_CLIENT_ID:
            raise RuntimeError("GRANOLA_OAUTH_CLIENT_ID is not set")
        return settings.GRANOLA_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.GRANOLA_OAUTH_CLIENT_SECRET:
            raise RuntimeError("GRANOLA_OAUTH_CLIENT_SECRET is not set")
        return settings.GRANOLA_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.GRANOLA_OAUTH_REDIRECT_URI:
            raise RuntimeError("GRANOLA_OAUTH_REDIRECT_URI is not set")
        return settings.GRANOLA_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def _token_set(self, payload: dict) -> TokenSet:
        expires_at = None
        if payload.get("expires_in"):
            expires_at = datetime.now(UTC) + timedelta(seconds=int(payload["expires_in"]))
        return TokenSet(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=expires_at,
            scopes=[s for s in (payload.get("scope") or "").split(" ") if s],
        )

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "redirect_uri": self._redirect_uri(),
                },
            )
            resp.raise_for_status()
            return self._token_set(resp.json())

    async def refresh(self, refresh_token: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                },
            )
            resp.raise_for_status()
            return self._token_set(resp.json())

    async def revoke(self, access_token: str) -> None:
        # No documented revoke endpoint; disconnecting just drops our token copy.
        return None

    async def fetch_account(self, access_token: str) -> AccountInfo:
        info = await self.account_info(access_token)
        return AccountInfo(email=info.get("email"), display_name=info.get("workspace_name"))

    async def account_info(self, access_token: str) -> dict:
        """{workspace_id, workspace_name, email} — also used to derive a Granola
        source's external_ref (the workspace id)."""
        async with httpx.AsyncClient(
            timeout=15.0, headers={"Authorization": f"Bearer {access_token}"}
        ) as client:
            resp = await client.get(ACCOUNT_URL)
            resp.raise_for_status()
            data = resp.json()
        return {
            "workspace_id": data.get("workspace_id") or data.get("id"),
            "workspace_name": data.get("workspace_name") or data.get("name") or "Granola",
            "email": data.get("email"),
        }
