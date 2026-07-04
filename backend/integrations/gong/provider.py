"""Gong OAuth provider (Gong Collective marketplace app).

Gong issues per-customer OAuth tokens: the token response carries an
`api_base_url_for_customer` that every later API call for that customer must
target — customers live on different data-center subdomains, so the generic
api.gong.io host doesn't work. The storage layer only hands callers back the
`access_token` string, so we bundle both values into it as JSON
(`{"access_token", "api_base_url"}`) — the same json-bundle the indexer already
json.loads(). Refresh re-bundles, so the base URL rides along for free.

Token exchange authenticates with HTTP Basic (client_id:client_secret); the
returned access token is then sent as a Bearer to the customer's base URL.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://app.gong.io/oauth2/authorize"
TOKEN_URL = "https://app.gong.io/oauth2/generate-customer-token"

# calls:read:basic lists calls + metadata; calls:read:transcript pulls the
# transcript text; workspaces:read backs the workspace allowlist and the
# connected-account label. These must match the scopes configured on the Gong
# app in the developer hub, or the authorize step is rejected.
SCOPES = [
    "api:calls:read:basic",
    "api:calls:read:transcript",
    "api:workspaces:read",
]


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


class GongIntegration(Integration):
    name = "gong"
    display_name = "Gong"
    scopes = SCOPES
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.GONG_OAUTH_CLIENT_ID:
            raise RuntimeError("GONG_OAUTH_CLIENT_ID is not set")
        return settings.GONG_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.GONG_OAUTH_CLIENT_SECRET:
            raise RuntimeError("GONG_OAUTH_CLIENT_SECRET is not set")
        return settings.GONG_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.GONG_OAUTH_REDIRECT_URI:
            raise RuntimeError("GONG_OAUTH_REDIRECT_URI is not set")
        return settings.GONG_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "redirect_uri": self._redirect_uri(),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri(),
            }
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        token = await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        # Gong may omit a new refresh token on refresh — preserve the existing one.
        if token.refresh_token is None:
            token.refresh_token = refresh_token
        return token

    async def _token_request(self, data: dict[str, str]) -> TokenSet:
        headers = {"Authorization": _basic_auth(self._client_id(), self._client_secret())}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.post(TOKEN_URL, data=data)
            resp.raise_for_status()
            payload = resp.json()
        return _payload_to_tokenset(payload)

    async def revoke(self, access_token: str) -> None:
        # Gong exposes no token-revocation endpoint; disconnect just drops our
        # stored row (storage.revoke_stored). Nothing to call upstream.
        return None

    async def fetch_account(self, access_token: str) -> AccountInfo:
        creds = json.loads(access_token)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(f"{creds['api_base_url']}/v2/workspaces")
            resp.raise_for_status()
            workspaces = resp.json().get("workspaces", [])
        display_name = workspaces[0]["name"] if workspaces else "Gong"
        return AccountInfo(email=None, display_name=display_name)


def _payload_to_tokenset(payload: dict) -> TokenSet:
    api_base_url = payload["api_base_url_for_customer"].rstrip("/")
    bundle = json.dumps({"access_token": payload["access_token"], "api_base_url": api_base_url})
    expires_in = payload.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
    scopes_raw = payload.get("scope") or ""
    return TokenSet(
        access_token=bundle,
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        scopes=[s for s in scopes_raw.split() if s],
    )
