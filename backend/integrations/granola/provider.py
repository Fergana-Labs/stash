"""Granola integration — OAuth 2.0 via the official MCP server.

Granola connects through `mcp.granola.ai` over OAuth 2.0 with Dynamic Client
Registration + PKCE (browser sign-in, no pasted key). The handshake doesn't fit
the generic sync `authorize_url(state)` → `exchange_code(code)` model, so this
provider advertises `auth_kind = "mcp_oauth"` and the router delegates the two
redirect endpoints to `start_authorization` / `finish_authorization` here (see
oauth.py). The generic OAuth methods are unused and raise.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from ..base import AccountInfo, TokenSet
from . import oauth

_GENERIC = "Granola uses the MCP OAuth flow (start_authorization/finish_authorization)."


class GranolaIntegration:
    name = "granola"
    display_name = "Granola"
    scopes = oauth.SCOPES.split()
    supports_refresh = True
    # Tells the router + UI to use the MCP OAuth redirect endpoints below
    # instead of the generic authorize_url/exchange_code path.
    auth_kind = "mcp_oauth"

    async def start_authorization(self, user_id: UUID, return_to: str | None) -> str:
        return await oauth.start_authorization(user_id, return_to)

    async def finish_authorization(self, code: str, state: str) -> str | None:
        return await oauth.finish_authorization(code, state)

    async def revoke(self, access_token: str) -> None:
        # Granola tokens are revoked by signing out in Granola; we drop our copy.
        return None

    async def get_valid_access_token(self, user_id: UUID) -> str:
        return await oauth.get_valid_access_token(user_id)

    # --- Unused generic OAuth surface (the mcp_oauth branch bypasses these) ---

    def authorize_url(self, state: str) -> str:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def exchange_code(self, code: str) -> TokenSet:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def fetch_account(self, access_token: str) -> AccountInfo:
        raise HTTPException(status_code=400, detail=_GENERIC)
