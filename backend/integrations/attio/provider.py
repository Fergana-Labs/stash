"""Attio OAuth provider (standard authorization-code app).

Attio access tokens do not expire and there is no refresh token
(`supports_refresh = False`) — same shape as GitHub user tokens. If the user
revokes the app in Attio, API calls return 401 and they must reconnect from the
integrations page.

The token exchange sends client_id/client_secret in the POST body; the returned
access token is then sent as a Bearer to api.attio.com. GET /v2/self identifies
the connected workspace (used for the account label).
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://app.attio.com/authorize"
TOKEN_URL = "https://app.attio.com/oauth/token"
SELF_URL = "https://api.attio.com/v2/self"

# meeting:read lists meetings; call_recording:read lists recordings and pulls
# their transcripts. These must match the scopes enabled on the Attio app in the
# developer dashboard, or the authorize step is rejected.
SCOPES = ["meeting:read", "call_recording:read"]


class AttioIntegration(Integration):
    name = "attio"
    display_name = "Attio"
    scopes = SCOPES
    supports_refresh = False

    def _client_id(self) -> str:
        if not settings.ATTIO_OAUTH_CLIENT_ID:
            raise RuntimeError("ATTIO_OAUTH_CLIENT_ID is not set")
        return settings.ATTIO_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.ATTIO_OAUTH_CLIENT_SECRET:
            raise RuntimeError("ATTIO_OAUTH_CLIENT_SECRET is not set")
        return settings.ATTIO_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.ATTIO_OAUTH_REDIRECT_URI:
            raise RuntimeError("ATTIO_OAUTH_REDIRECT_URI is not set")
        return settings.ATTIO_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        return TokenSet(
            access_token=payload["access_token"],
            refresh_token=None,
            expires_at=None,
            scopes=(payload.get("scope") or "").split(),
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise RuntimeError("Attio access tokens are not refreshable")

    async def revoke(self, access_token: str) -> None:
        # Attio exposes no token-revocation endpoint; disconnect just drops our
        # stored row (storage.revoke_stored). Nothing to call upstream.
        return None

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(SELF_URL)
            resp.raise_for_status()
            info = resp.json()
        return AccountInfo(email=None, display_name=info.get("workspace_name") or "Attio")
