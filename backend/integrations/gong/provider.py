"""Gong api_key provider.

Gong authenticates per customer with an Access Key + Secret (HTTP Basic),
not OAuth — Gong OAuth is gated on marketplace-partner approval. The user
pastes both in the connect form; we validate them against /v2/workspaces and
store the bundle as the access token (see integrations/base.py for the
api_key contract).
"""

from __future__ import annotations

import base64
import json

import httpx

from ..base import AccountInfo, CredentialField, TokenSet

API_BASE = "https://api.gong.io"


def basic_auth_header(access_key: str, secret: str) -> str:
    raw = f"{access_key}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


class GongIntegration:
    name = "gong"
    display_name = "Gong"
    scopes: list[str] = []
    supports_refresh = False
    auth_kind = "api_key"
    credential_fields = [
        CredentialField("access_key", "Access Key", secret=True, placeholder="Gong API access key"),
        CredentialField(
            "access_key_secret", "Access Key Secret", secret=True, placeholder="Gong API secret"
        ),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        access_key = (values.get("access_key") or "").strip()
        secret = (values.get("access_key_secret") or "").strip()
        if not access_key or not secret:
            raise ValueError("Both Access Key and Access Key Secret are required")

        headers = {"Authorization": basic_auth_header(access_key, secret)}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(f"{API_BASE}/v2/workspaces")
        # Any non-200 means we couldn't validate the keys — a client error, so
        # surface it as ValueError (the router maps it to 400) rather than 500.
        if resp.status_code != 200:
            raise ValueError(f"Gong rejected these credentials (HTTP {resp.status_code})")
        workspaces = resp.json().get("workspaces", [])

        display_name = workspaces[0]["name"] if workspaces else "Gong"
        token = TokenSet(
            access_token=json.dumps({"access_key": access_key, "access_key_secret": secret}),
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token, AccountInfo(email=None, display_name=display_name)
