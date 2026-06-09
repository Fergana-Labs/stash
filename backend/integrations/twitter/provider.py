"""Twitter / X api_key provider.

X's OAuth 2.0 user flow requires PKCE. Stash's simple credential-provider path
is a better first fit here: users paste an X API bearer token, and agents use it
read-only for public v2 endpoints.
"""

from __future__ import annotations

import httpx

from ..base import AccountInfo, CredentialField, TokenSet

API_BASE = "https://api.x.com"
VALIDATION_URL = f"{API_BASE}/2/users/by/username/XDevelopers"


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

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(VALIDATION_URL, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            raise ValueError(f"X rejected this bearer token (HTTP {resp.status_code})")

        token_set = TokenSet(
            access_token=token,
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token_set, AccountInfo(email=None, display_name="X API")

    async def revoke(self, access_token: str) -> None:
        return None
