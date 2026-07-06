"""Asana OAuth provider.

Standard OAuth 2.0 with rotating refresh tokens (access tokens last ~1h).
storage.get_valid_token refreshes on use and COALESCEs the rotated refresh
token back in. The granular read scopes below require the Asana app to be
configured for granular permissions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://app.asana.com/-/oauth_authorize"
TOKEN_URL = "https://app.asana.com/-/oauth_token"
REVOKE_URL = "https://app.asana.com/-/oauth_revoke"
ME_URL = "https://app.asana.com/api/1.0/users/me"


class AsanaIntegration(Integration):
    name = "asana"
    display_name = "Asana"
    scopes = ["projects:read", "tasks:read", "users:read", "workspaces:read"]
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.ASANA_OAUTH_CLIENT_ID:
            raise RuntimeError("ASANA_OAUTH_CLIENT_ID is not set")
        return settings.ASANA_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.ASANA_OAUTH_CLIENT_SECRET:
            raise RuntimeError("ASANA_OAUTH_CLIENT_SECRET is not set")
        return settings.ASANA_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.ASANA_OAUTH_REDIRECT_URI:
            raise RuntimeError("ASANA_OAUTH_REDIRECT_URI is not set")
        return settings.ASANA_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "state": state,
            "scope": " ".join(self.scopes),
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def _token_request(self, payload: dict) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, data=payload)
            # httpx.HTTPStatusError so a dead grant is classified as
            # needs_reconnect by _account_needs_reconnect instead of a 500.
            resp.raise_for_status()
            data = resp.json()
        expires_in = data.get("expires_in")
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None
        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=self.scopes,
        )

    async def exchange_code(self, code: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "redirect_uri": self._redirect_uri(),
                "code": code,
            }
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "refresh_token": refresh_token,
            }
        )

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                REVOKE_URL,
                data={
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "token": access_token,
                },
            )

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(ME_URL)
            resp.raise_for_status()
            me = resp.json().get("data", {})
        return AccountInfo(email=me.get("email"), display_name=me.get("name"))
