"""Integration base contract.

Every third-party provider implements this protocol. The OAuth router
and the token storage layer only talk to providers through this surface
— they never know the difference between Google and GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class TokenSet:
    """OAuth tokens returned by exchange/refresh."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None  # None = does not expire (e.g. GitHub user tokens)
    scopes: list[str]


@dataclass
class AccountInfo:
    """Identity surface shown back to the user in the integration card."""

    email: str | None
    display_name: str | None


class Integration(Protocol):
    name: str
    """URL segment + provider key. e.g. 'google', 'github'."""

    display_name: str
    """Human-readable name shown in the UI. e.g. 'Google', 'GitHub'."""

    scopes: list[str]
    """OAuth scopes requested at consent time."""

    supports_refresh: bool
    """True if the provider issues refresh tokens. Google yes, GitHub user
    tokens no (they're long-lived but not refreshable)."""

    def authorize_url(self, state: str) -> str:
        """URL to redirect the user to for consent. `state` is the CSRF nonce."""
        ...

    async def exchange_code(self, code: str) -> TokenSet:
        """Exchange the authorization code for an access (and refresh) token."""
        ...

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Exchange a refresh token for a new access token. Raises if !supports_refresh."""
        ...

    async def revoke(self, access_token: str) -> None:
        """Tell the provider to invalidate this token."""
        ...

    async def fetch_account(self, access_token: str) -> AccountInfo:
        """Resolve the connected account identity for display."""
        ...
