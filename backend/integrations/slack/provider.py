"""Slack OAuth provider (OAuth v2).

We store the **user** token (`authed_user.access_token`), not the bot token —
reading a member's channels/history to index them needs the user token. Slack
user tokens don't expire unless token rotation is enabled on the app, so
`supports_refresh = False`.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
TOKEN_URL = "https://slack.com/api/oauth.v2.access"
AUTH_TEST_URL = "https://slack.com/api/auth.test"
REVOKE_URL = "https://slack.com/api/auth.revoke"

# User-token scopes: list conversations + read their history + resolve user
# names. The `*:read` scopes are required by conversations.list (the backfill
# enumerates channels); `*:history` lets us read messages. We index rather than
# search live, so search:read is not required.
USER_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
]

# --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
# Bot scopes requested in the same install so we also receive a team bot
# token. They power the conversational agent (mentions/DMs → reply), separate
# from the user-token ingest above. To drop the Slack agent: remove these
# scopes, the `scope=` param in authorize_url, and the install capture in
# exchange_code (plus integrations/slack/{installs,client,agent}.py).
BOT_SCOPES = [
    "app_mentions:read",  # receive @mentions
    "chat:write",  # post replies
    "im:history",  # read DMs to the bot
    "im:read",
    "im:write",  # open/post DMs
    "users:read",
    "users:read.email",  # resolve Slack user → email → Stash account
]
# --- END Slack agent ---


class SlackIntegration(Integration):
    name = "slack"
    display_name = "Slack"
    scopes = USER_SCOPES
    supports_refresh = False

    def _client_id(self) -> str:
        if not settings.SLACK_OAUTH_CLIENT_ID:
            raise RuntimeError("SLACK_OAUTH_CLIENT_ID is not set")
        return settings.SLACK_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.SLACK_OAUTH_CLIENT_SECRET:
            raise RuntimeError("SLACK_OAUTH_CLIENT_SECRET is not set")
        return settings.SLACK_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.SLACK_OAUTH_REDIRECT_URI:
            raise RuntimeError("SLACK_OAUTH_REDIRECT_URI is not set")
        return settings.SLACK_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "user_scope": " ".join(self.scopes),
            # Slack agent: `scope` requests bot scopes → install yields a bot token too.
            "scope": " ".join(BOT_SCOPES),
            "redirect_uri": self._redirect_uri(),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Slack OAuth error: {payload.get('error')}")

        # --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
        # The same install yields a team bot token at top-level `access_token`
        # (present only because we request bot `scope`). Store it so the agent
        # can post replies. Failure here must not block the user-token connect.
        from . import installs

        bot_token = payload.get("access_token")
        team_id = (payload.get("team") or {}).get("id")
        if bot_token and team_id:
            await installs.store_install(
                team_id=team_id,
                bot_token=bot_token,
                bot_user_id=payload.get("bot_user_id"),
            )
        # --- END Slack agent ---

        authed_user = payload.get("authed_user") or {}
        user_token = authed_user.get("access_token")
        if not user_token:
            raise RuntimeError("Slack OAuth returned no user token (check user_scope)")
        return TokenSet(
            access_token=user_token,
            refresh_token=None,
            expires_at=None,
            scopes=[s for s in (authed_user.get("scope") or "").split(",") if s],
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise RuntimeError("Slack user tokens are not refreshable")

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(REVOKE_URL, headers={"Authorization": f"Bearer {access_token}"})

    async def fetch_account(self, access_token: str) -> AccountInfo:
        info = await self.team_info(access_token)
        return AccountInfo(
            email=None,
            display_name=info["team_name"],
            account_ref=info["team_id"],
        )

    async def team_info(self, access_token: str) -> dict:
        """auth.test → {team_id, team_name, user_id}. Used both for the account
        card and to derive a Slack source's external_ref (the team id)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                AUTH_TEST_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            resp.raise_for_status()
            payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Slack auth.test error: {payload.get('error')}")
        return {
            "team_id": payload.get("team_id"),
            "team_name": payload.get("team"),
            "user_id": payload.get("user_id"),
        }
