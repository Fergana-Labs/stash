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
    """Identity surface shown back to the user in the integration card.

    account_ref is the provider's STABLE account id (X user id, Google email,
    GitHub login) — the anchor for the reconnect identity check. Providers
    that can supply it must; without it a reconnect under a different account
    cannot be detected."""

    email: str | None
    display_name: str | None
    account_ref: str | None = None


@dataclass
class CredentialField:
    """One input in an api_key provider's connect form (see below)."""

    name: str
    label: str
    secret: bool = False  # render as a password field + never echo back
    placeholder: str = ""
    optional: bool = False  # not required to submit the form
    help: str = ""  # one-line hint shown under the field


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


# --- api_key providers -------------------------------------------------------
#
# Some services authenticate with pasted credentials, not an OAuth redirect.
# Such a provider sets `auth_kind = "api_key"`, declares its
# `credential_fields`, and implements `connect_with_credentials` instead of the
# OAuth methods. The router renders a form from the fields and POSTs the values
# to /credentials. The provider validates them against the upstream and returns
# the credential bundle as the access token (JSON-encoded, with no expiry) so it
# rides the same encrypted storage column as OAuth tokens — callers recover it
# with `json.loads(await get_valid_token(...))`.
#
#   class GongIntegration:
#       name = "gong"
#       display_name = "Gong"
#       auth_kind = "api_key"
#       credential_fields = [CredentialField("access_key", "Access Key", secret=True), ...]
#       async def connect_with_credentials(self, values: dict[str, str])
#           -> tuple[TokenSet, AccountInfo]: ...
