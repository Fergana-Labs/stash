"""Twitter / X OAuth provider.

X's OAuth 2.0 user flow requires PKCE. The router stores the code verifier in
our encrypted state blob, then passes it back for the token exchange.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

API_BASE = "https://api.x.com"
AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = f"{API_BASE}/2/oauth2/token"
REVOKE_URL = f"{API_BASE}/2/oauth2/revoke"
ME_URL = f"{API_BASE}/2/users/me"


class TwitterIntegration(Integration):
    name = "twitter"
    display_name = "Twitter / X"
    scopes = [
        "tweet.read",
        "users.read",
        "bookmark.read",
        "like.read",
        "dm.read",
        "offline.access",
    ]
    supports_refresh = True
    uses_pkce = True

    def _client_id(self, override: str | None = None) -> str:
        # A bring-your-own-app user supplies their own client id (so bookmark
        # reads hit their paid quota); everyone else uses Stash's app.
        if override:
            return override
        if not settings.TWITTER_OAUTH_CLIENT_ID:
            raise RuntimeError("TWITTER_OAUTH_CLIENT_ID is not set")
        return settings.TWITTER_OAUTH_CLIENT_ID

    def _client_secret(self, override: str | None = None) -> str | None:
        if override:
            return override
        return settings.TWITTER_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.TWITTER_OAUTH_REDIRECT_URI:
            raise RuntimeError("TWITTER_OAUTH_REDIRECT_URI is not set")
        return settings.TWITTER_OAUTH_REDIRECT_URI

    def new_code_verifier(self) -> str:
        return secrets.token_urlsafe(64)

    def authorize_url(self, state: str, code_verifier: str, *, client_id: str | None = None) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        params = {
            "response_type": "code",
            "client_id": self._client_id(client_id),
            "redirect_uri": self._redirect_uri(),
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                auth=self._token_auth(client_id, client_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                    "client_id": self._client_id(client_id),
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        return _payload_to_tokenset(payload)

    async def refresh(
        self,
        refresh_token: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                auth=self._token_auth(client_id, client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._client_id(client_id),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        token = _payload_to_tokenset(payload)
        if token.refresh_token is None:
            token.refresh_token = refresh_token
        return token

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                REVOKE_URL,
                auth=self._token_auth(),
                data={
                    "token": access_token,
                    "client_id": self._client_id(),
                    "token_type_hint": "access_token",
                },
            )
            if resp.status_code not in (200, 400):
                resp.raise_for_status()

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(ME_URL, params={"user.fields": "username,name"})
            resp.raise_for_status()
            payload = resp.json()
        user = payload.get("data") or {}
        username = user.get("username")
        display_name = f"@{username}" if username else user.get("name")
        return AccountInfo(email=None, display_name=display_name)

    def _token_auth(
        self, client_id: str | None = None, client_secret: str | None = None
    ) -> tuple[str, str] | None:
        secret = self._client_secret(client_secret)
        if not secret:
            return None
        return (self._client_id(client_id), secret)


def _payload_to_tokenset(payload: dict) -> TokenSet:
    expires_in = payload.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
    scopes_raw = payload.get("scope") or ""
    return TokenSet(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        scopes=[s for s in scopes_raw.split() if s],
    )
