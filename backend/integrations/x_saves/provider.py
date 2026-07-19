"""X (Twitter) OAuth provider.

X's OAuth 2.0 user flow requires PKCE — the router stores the code verifier in
our encrypted state blob and passes it back for the token exchange. We ask for
`bookmark.read` so the indexer can read the user's own bookmarks; posts/replies
come from twitterapi.io by handle, so no timeline scopes are needed here.
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


class XIntegration(Integration):
    name = "x"
    display_name = "X"
    scopes = ["tweet.read", "users.read", "bookmark.read", "offline.access"]
    supports_refresh = True
    uses_pkce = True

    def _client_id(self) -> str:
        if not settings.TWITTER_OAUTH_CLIENT_ID:
            raise RuntimeError("TWITTER_OAUTH_CLIENT_ID is not set")
        return settings.TWITTER_OAUTH_CLIENT_ID

    def _redirect_uri(self) -> str:
        if not settings.TWITTER_OAUTH_REDIRECT_URI:
            raise RuntimeError("TWITTER_OAUTH_REDIRECT_URI is not set")
        return settings.TWITTER_OAUTH_REDIRECT_URI

    def _token_auth(self) -> tuple[str, str] | None:
        secret = settings.TWITTER_OAUTH_CLIENT_SECRET
        return (self._client_id(), secret) if secret else None

    def new_code_verifier(self) -> str:
        return secrets.token_urlsafe(64)

    def authorize_url(self, state: str, code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        params = {
            "response_type": "code",
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                auth=self._token_auth(),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                    "client_id": self._client_id(),
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        return _payload_to_tokenset(payload)

    async def refresh(self, refresh_token: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                auth=self._token_auth(),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._client_id(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        token = _payload_to_tokenset(payload)
        if token.refresh_token is None:
            token.refresh_token = refresh_token
        return token

    async def fetch_account(self, access_token: str) -> AccountInfo:
        user = await fetch_me(access_token)
        username = user.get("username")
        display_name = f"@{username}" if username else user.get("name")
        return AccountInfo(email=None, display_name=display_name)


async def fetch_me(access_token: str) -> dict:
    """The connected X account (id, username). /users/me is X's most
    rate-limited endpoint, so this is called once at connect time; the id is
    stored on the source afterwards."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        resp = await client.get(ME_URL, params={"user.fields": "username,name"})
    resp.raise_for_status()
    user = resp.json().get("data") or {}
    if not user.get("id"):
        raise RuntimeError("X did not return the connected user id")
    return user


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
