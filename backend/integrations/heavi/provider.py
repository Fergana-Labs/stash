"""Heavi api_key provider (bring-your-own learnings endpoint).

Heavi customers paste their learnings endpoint URL + API token instead of
doing an OAuth dance. Connect validates the pair by fetching the learnings
once, then stores both as a JSON bundle in the access-token column (the
same json-bundle pattern Gong uses for its per-customer base URL) —
`client.fetch_learnings` recovers it with json.loads.
"""

from __future__ import annotations

import json

from ..base import AccountInfo, CredentialField, TokenSet
from .client import fetch_learnings_with


class HeaviIntegration:
    name = "heavi"
    display_name = "Heavi"
    scopes: list[str] = []
    supports_refresh = False
    auth_kind = "api_key"
    # Customer-specific integration: only Heavi accounts see or connect it —
    # verified @heaviai.com emails and the Heavi workspace's scope user
    # (enforced by _user_may_use_provider in the integrations router).
    allowed_email_domains = ("heaviai.com",)
    credential_fields = [
        CredentialField(
            name="base_url",
            label="Learnings endpoint URL",
            placeholder="https://app.heaviai.com/api/stash/learnings",
            help="The GET endpoint that returns your org's rules of the road as JSON.",
        ),
        CredentialField(
            name="api_token",
            label="API token",
            secret=True,
            help="Bearer token the endpoint accepts.",
        ),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        base_url = values.get("base_url", "").strip().rstrip("/")
        api_token = values.get("api_token", "").strip()
        if not base_url.startswith("https://"):
            raise ValueError("base_url must be an https:// URL")
        if not api_token:
            raise ValueError("api_token is required")
        learnings = await fetch_learnings_with(base_url, api_token)
        bundle = json.dumps({"base_url": base_url, "api_token": api_token})
        token = TokenSet(access_token=bundle, refresh_token=None, expires_at=None, scopes=[])
        count = len(learnings)
        account = AccountInfo(
            email=None,
            display_name=f"Rules of the Road ({count} rule{'s' if count != 1 else ''})",
        )
        return token, account

    async def revoke(self, access_token: str) -> None:
        # Heavi exposes no token-revocation endpoint; disconnect just drops
        # our stored row. Nothing to call upstream.
        return None
