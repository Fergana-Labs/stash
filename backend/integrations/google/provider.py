"""Google OAuth provider.

Refresh tokens are issued only on the FIRST consent for a user — Google
requires `access_type=offline` and `prompt=consent` to guarantee one
each time. We request both so reconnecting always lands a new refresh
token, replacing the stored one if present.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleIntegration(Integration):
    name = "google"
    display_name = "Google"
    # drive.readonly: read Docs/Sheets/PPTX for import
    # drive.file: create files in user's Drive for Slides export
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "openid",
        "email",
        "profile",
    ]
    supports_refresh = True

    def _client_id(self) -> str:
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID is not set")
        return settings.GOOGLE_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_SECRET is not set")
        return settings.GOOGLE_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.GOOGLE_OAUTH_REDIRECT_URI:
            raise RuntimeError("GOOGLE_OAUTH_REDIRECT_URI is not set")
        return settings.GOOGLE_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "redirect_uri": self._redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        return _payload_to_tokenset(payload)

    async def refresh(self, refresh_token: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        # Google omits refresh_token on refresh — preserve the existing one.
        token = _payload_to_tokenset(payload)
        if token.refresh_token is None:
            token.refresh_token = refresh_token
        return token

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(REVOKE_URL, data={"token": access_token})
            if resp.status_code not in (200, 400):
                # 400 just means already revoked / unknown — treat as success.
                resp.raise_for_status()

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(USERINFO_URL)
            resp.raise_for_status()
            payload = resp.json()
        return AccountInfo(email=payload.get("email"), display_name=payload.get("name"))


def _payload_to_tokenset(payload: dict) -> TokenSet:
    expires_in = payload.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )
    scopes_raw = payload.get("scope") or ""
    scopes = [s for s in scopes_raw.split() if s]
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        scopes=scopes,
    )
