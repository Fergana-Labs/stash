"""GitHub OAuth provider.

GitHub user access tokens for OAuth apps don't expire by default
(`supports_refresh = False`). If the user revokes our app, /user calls
return 401 and the user must reconnect from the integrations page.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import settings
from ..base import AccountInfo, Integration, TokenSet

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
USER_EMAILS_URL = "https://api.github.com/user/emails"


class GitHubIntegration(Integration):
    name = "github"
    display_name = "GitHub"
    scopes = ["repo"]  # read private repos (used for zipball import)
    supports_refresh = False

    def _client_id(self) -> str:
        if not settings.GITHUB_OAUTH_CLIENT_ID:
            raise RuntimeError("GITHUB_OAUTH_CLIENT_ID is not set")
        return settings.GITHUB_OAUTH_CLIENT_ID

    def _client_secret(self) -> str:
        if not settings.GITHUB_OAUTH_CLIENT_SECRET:
            raise RuntimeError("GITHUB_OAUTH_CLIENT_SECRET is not set")
        return settings.GITHUB_OAUTH_CLIENT_SECRET

    def _redirect_uri(self) -> str:
        if not settings.GITHUB_OAUTH_REDIRECT_URI:
            raise RuntimeError("GITHUB_OAUTH_REDIRECT_URI is not set")
        return settings.GITHUB_OAUTH_REDIRECT_URI

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id(),
            "redirect_uri": self._redirect_uri(),
            "scope": " ".join(self.scopes),
            "state": state,
            "allow_signup": "false",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenSet:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self._client_id(),
                    "client_secret": self._client_secret(),
                    "code": code,
                    "redirect_uri": self._redirect_uri(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        if "error" in payload:
            raise RuntimeError(
                f"GitHub OAuth error: {payload.get('error_description') or payload['error']}"
            )
        return TokenSet(
            access_token=payload["access_token"],
            refresh_token=None,
            expires_at=None,
            scopes=[s for s in (payload.get("scope") or "").split(",") if s],
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise RuntimeError("GitHub OAuth user tokens are not refreshable")

    async def revoke(self, access_token: str) -> None:
        # https://docs.github.com/en/rest/apps/oauth-applications#delete-an-app-token
        url = f"https://api.github.com/applications/{self._client_id()}/token"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                "DELETE",
                url,
                auth=(self._client_id(), self._client_secret()),
                headers={"Accept": "application/vnd.github+json"},
                json={"access_token": access_token},
            )
            # 204 success, 422 already invalid — both fine.
            if resp.status_code not in (204, 422):
                resp.raise_for_status()

    async def fetch_account(self, access_token: str) -> AccountInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            user_resp = await client.get(USER_URL)
            user_resp.raise_for_status()
            user = user_resp.json()
            email = user.get("email")
            if not email:
                # /user only returns email if it's set as public — fall back
                # to /user/emails for the primary verified one.
                emails_resp = await client.get(USER_EMAILS_URL)
                if emails_resp.status_code == 200:
                    for e in emails_resp.json():
                        if e.get("primary") and e.get("verified"):
                            email = e.get("email")
                            break
        return AccountInfo(
            email=email,
            display_name=user.get("name") or user.get("login"),
            account_ref=user.get("login"),
        )
