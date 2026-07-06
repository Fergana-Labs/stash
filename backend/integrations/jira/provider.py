"""Jira (Atlassian) OAuth provider.

Atlassian 3LO OAuth 2.0. `offline_access` gets us a refresh token, and
Atlassian rotates it on every refresh — storage.get_valid_token COALESCEs
the new one back in, so rotation is handled for free.

Jira's REST API is addressed per *cloud id* (one per Atlassian site). We
don't store the cloud id on the integration; it rides in each source's
external_ref as "{cloudId}:{projectKey}" (see indexer.py + the projects
picker in router.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ME_URL = "https://api.atlassian.com/me"


class JiraIntegration(Integration):
    name = "jira"
    display_name = "Jira"
    # read:jira-work covers issues + projects; offline_access yields a refresh token.
    scopes = ["read:jira-work", "read:jira-user", "offline_access"]
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.JIRA_OAUTH_CLIENT_ID:
            raise RuntimeError("JIRA_OAUTH_CLIENT_ID is not set")
        return settings.JIRA_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.JIRA_OAUTH_CLIENT_SECRET:
            raise RuntimeError("JIRA_OAUTH_CLIENT_SECRET is not set")
        return settings.JIRA_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.JIRA_OAUTH_REDIRECT_URI:
            raise RuntimeError("JIRA_OAUTH_REDIRECT_URI is not set")
        return settings.JIRA_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "audience": "api.atlassian.com",
            "client_id": self._client_id(),
            "scope": " ".join(self.scopes),
            "redirect_uri": self._redirect_uri(),
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def _token_request(self, payload: dict) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, json=payload)
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
            scopes=(data.get("scope") or "").split(),
        )

    async def exchange_code(self, code: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": self._client_id(),
                "client_secret": self._client_secret(),
                "code": code,
                "redirect_uri": self._redirect_uri(),
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
        # Atlassian has no token-revocation endpoint for 3LO apps; the user
        # revokes access from their Atlassian account settings. We still drop
        # our local copy in storage so they can reconnect cleanly.
        return None

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(ME_URL)
            resp.raise_for_status()
            me = resp.json()
        return AccountInfo(email=me.get("email"), display_name=me.get("name"))
