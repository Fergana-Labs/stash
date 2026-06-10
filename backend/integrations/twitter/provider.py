"""Twitter / X api_key provider.

X's OAuth 2.0 user flow requires PKCE. Stash's simple credential-provider path
is a better first fit here: users paste an X API bearer token, and agents use it
read-only for public v2 endpoints.
"""

from __future__ import annotations

import httpx

from ..base import AccountInfo, CredentialField, TokenSet

API_BASE = "https://api.x.com"
# Validate against recent search — the capability the source actually uses.
# A token can pass cheaper endpoints (user lookup) yet lack search access on
# some X plans, which would connect fine and then silently return no results.
VALIDATION_URL = f"{API_BASE}/2/tweets/search/recent"


class TwitterIntegration:
    name = "twitter"
    display_name = "Twitter / X"
    scopes: list[str] = []
    supports_refresh = False
    auth_kind = "api_key"
    credential_fields = [
        CredentialField(
            "bearer_token",
            "Bearer token",
            secret=True,
            placeholder="X API bearer token",
            help="Read-only token from the X Developer Portal.",
        ),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        token = (values.get("bearer_token") or "").strip()
        if not token:
            raise ValueError("Bearer token is required")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    VALIDATION_URL,
                    params={"query": "hello", "max_results": 10},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as e:
            # Transport failure, not a bad token — the router maps ValueError
            # to a 400 with a message instead of an opaque 500.
            raise ValueError(f"Could not reach X to validate the token — try again ({e})")
        if resp.status_code == 429:
            # A 429 means X authenticated the token and then rate-limited it
            # (invalid tokens get 401). Accept it: the free tier allows one
            # recent-search per 15 minutes, so rejecting here would lock out
            # legitimate (re)connects for the whole window.
            pass
        elif resp.status_code != 200:
            raise ValueError(
                f"X rejected this bearer token for recent search (HTTP {resp.status_code})"
            )

        token_set = TokenSet(
            access_token=token,
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token_set, AccountInfo(email=None, display_name="X API")
