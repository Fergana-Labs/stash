"""PostHog integration via OAuth 2.0 and the official MCP server."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from ..base import AccountInfo, TokenSet
from . import oauth

_GENERIC = "PostHog uses the MCP OAuth flow."


class PostHogIntegration:
    name = "posthog"
    display_name = "PostHog"
    auth_kind = "mcp_oauth"
    scopes = oauth.SCOPES.split()
    supports_refresh = True

    async def start_authorization(self, user_id: UUID, return_to: str | None) -> str:
        return await oauth.start_authorization(user_id, return_to)

    async def finish_authorization(self, code: str, state: str) -> str | None:
        return await oauth.finish_authorization(code, state)

    async def revoke(self, access_token: str) -> None:
        await oauth.revoke(access_token)

    async def get_valid_access_token(self, user_id: UUID) -> str:
        return await oauth.get_valid_access_token(user_id)

    def authorize_url(self, state: str) -> str:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def exchange_code(self, code: str) -> TokenSet:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def refresh(self, refresh_token: str) -> TokenSet:
        raise HTTPException(status_code=400, detail=_GENERIC)

    async def fetch_account(self, access_token: str) -> AccountInfo:
        raise HTTPException(status_code=400, detail=_GENERIC)
