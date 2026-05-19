"""Notion OAuth provider.

Notion's public OAuth grants a `bot_user` token scoped to whatever
pages/databases the workspace owner explicitly shared with our app
during install. Tokens don't expire (`supports_refresh = False`); the
user must reconnect to extend access (e.g. share more pages).

Token endpoint expects HTTP Basic with `client_id:client_secret`.
"""

from __future__ import annotations

from base64 import b64encode
from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"
ME_URL = "https://api.notion.com/v1/users/me"
NOTION_API_VERSION = "2022-06-28"


class NotionIntegration(Integration):
    name = "notion"
    display_name = "Notion"
    scopes: list[str] = []  # Notion uses workspace-level share, not OAuth scopes
    supports_refresh = False

    def _client_id(self) -> str:
        if not settings.NOTION_OAUTH_CLIENT_ID:
            raise RuntimeError("NOTION_OAUTH_CLIENT_ID is not set")
        return settings.NOTION_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.NOTION_OAUTH_CLIENT_SECRET:
            raise RuntimeError("NOTION_OAUTH_CLIENT_SECRET is not set")
        return settings.NOTION_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.NOTION_OAUTH_REDIRECT_URI:
            raise RuntimeError("NOTION_OAUTH_REDIRECT_URI is not set")
        return settings.NOTION_OAUTH_REDIRECT_URI

    def _basic_auth(self) -> str:
        raw = f"{self._client_id()}:{self._client_secret()}".encode()
        return f"Basic {b64encode(raw).decode()}"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "response_type": "code",
            "owner": "user",
            "redirect_uri": self._redirect_uri(),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth(),
                    "Content-Type": "application/json",
                    "Notion-Version": NOTION_API_VERSION,
                },
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        return TokenSet(
            access_token=payload["access_token"],
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise RuntimeError("Notion OAuth tokens are not refreshable")

    async def revoke(self, access_token: str) -> None:
        # Notion's public API has no token-revocation endpoint. Deleting
        # the row in storage is the closest we can get; the user can
        # also remove the integration from their workspace settings.
        return

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": NOTION_API_VERSION,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(ME_URL)
            resp.raise_for_status()
            payload = resp.json()
        bot = payload.get("bot", {}) or {}
        owner = bot.get("owner", {}) or {}
        user = owner.get("user", {}) or {}
        # Public API returns either bot.workspace_name or a user record
        # depending on how the integration was installed. Prefer whichever
        # surfaces useful identity info to the user.
        person = user.get("person", {}) or {}
        return AccountInfo(
            email=person.get("email"),
            display_name=user.get("name") or bot.get("workspace_name") or "Notion workspace",
        )
