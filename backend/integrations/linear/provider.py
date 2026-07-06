"""Linear OAuth provider.

Linear migrated all OAuth apps to 24-hour access tokens with rotating refresh
tokens on 2026-04-01, so supports_refresh is True; storage.get_valid_token
refreshes on use and COALESCEs the rotated refresh token back in. The
connected token is what reads issues for ticket enrichment
(backend/services/linear_ticket_service.py); the inbound webhook in
backend/routers/webhooks.py keeps those labels fresh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://linear.app/oauth/authorize"
TOKEN_URL = "https://api.linear.app/oauth/token"
REVOKE_URL = "https://api.linear.app/oauth/revoke"
VIEWER_QUERY = "query { viewer { name email } }"


class LinearIntegration(Integration):
    name = "linear"
    display_name = "Linear"
    # `read` covers issue lookups; app-level webhooks are delivered regardless of scope.
    scopes = ["read"]
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.LINEAR_OAUTH_CLIENT_ID:
            raise RuntimeError("LINEAR_OAUTH_CLIENT_ID is not set")
        return settings.LINEAR_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.LINEAR_OAUTH_CLIENT_SECRET:
            raise RuntimeError("LINEAR_OAUTH_CLIENT_SECRET is not set")
        return settings.LINEAR_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.LINEAR_OAUTH_REDIRECT_URI:
            raise RuntimeError("LINEAR_OAUTH_REDIRECT_URI is not set")
        return settings.LINEAR_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": ",".join(self.scopes),
            "state": state,
            "prompt": "consent",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def _token_request(self, payload: dict) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, data=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Linear token endpoint returned status_code={resp.status_code}")
            data = resp.json()
        expires_in = data.get("expires_in")
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None
        scope = data.get("scope") or ""
        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=scope.split(",") if scope else list(self.scopes),
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
            await client.post(REVOKE_URL, headers={"Authorization": f"Bearer {access_token}"})

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.post(settings.LINEAR_API_URL, json={"query": VIEWER_QUERY})
            resp.raise_for_status()
            viewer = (resp.json().get("data") or {}).get("viewer") or {}
        return AccountInfo(email=viewer.get("email"), display_name=viewer.get("name"))
