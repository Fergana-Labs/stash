"""Render api_key provider.

Render's hosted MCP server does not support OAuth yet — clients send an
account API key as a bearer header. The user pastes the key in the connect
form; we validate it against Render's REST API and store it as the access
token. The MCP proxy (backend/services/mcp_proxy_service.py) reads it back
to authenticate proxied tool calls.
"""

from __future__ import annotations

import httpx

from ..base import AccountInfo, CredentialField, TokenSet

API_BASE = "https://api.render.com"


class RenderIntegration:
    name = "render"
    display_name = "Render"
    scopes: list[str] = []
    supports_refresh = False
    auth_kind = "api_key"
    credential_fields = [
        CredentialField(
            "api_key",
            "API key",
            secret=True,
            placeholder="rnd_…",
            help="Create one at dashboard.render.com → Account Settings → API Keys.",
        ),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        api_key = (values.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key is required")

        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(f"{API_BASE}/v1/owners", params={"limit": 1})
        if resp.status_code != 200:
            raise ValueError(f"Render rejected this API key (HTTP {resp.status_code})")
        owners = resp.json()

        owner = owners[0]["owner"] if owners else {}
        token = TokenSet(
            access_token=api_key,
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token, AccountInfo(
            email=owner.get("email"), display_name=owner.get("name") or "Render"
        )
