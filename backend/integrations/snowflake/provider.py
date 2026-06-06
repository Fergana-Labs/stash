"""Snowflake api_key provider.

Snowflake is a SQL warehouse, exposed to the agent as a read-only *query*
source rather than a crawled document source. Credentials are pasted (key-pair
auth recommended — Snowflake is phasing out single-factor passwords for service
accounts; a password field is accepted as an alternative). See client.py for
the read-only query path and integrations/base.py for the api_key contract.
"""

from __future__ import annotations

import json

from ..base import AccountInfo, CredentialField, TokenSet
from .client import test_connection


class SnowflakeIntegration:
    name = "snowflake"
    display_name = "Snowflake"
    scopes: list[str] = []
    supports_refresh = False
    auth_kind = "api_key"
    credential_fields = [
        CredentialField("account", "Account", placeholder="orgname-account_name"),
        CredentialField("user", "User", placeholder="SVC_AGENT"),
        CredentialField(
            "private_key",
            "Private Key (PEM)",
            secret=True,
            placeholder="-----BEGIN PRIVATE KEY-----",
        ),
        CredentialField("private_key_passphrase", "Private Key Passphrase", secret=True),
        CredentialField("warehouse", "Warehouse", placeholder="COMPUTE_WH"),
        CredentialField("role", "Role", placeholder="READ_ONLY"),
        CredentialField("database", "Database", placeholder="(optional default)"),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        creds = {k: v.strip() for k, v in values.items() if v and v.strip()}
        if not creds.get("account") or not creds.get("user"):
            raise ValueError("Account and User are required")
        if not creds.get("private_key") and not creds.get("password"):
            raise ValueError("A private key (or password) is required")

        try:
            display_name = await test_connection(creds)
        except ValueError:
            raise
        except Exception as e:
            # Connection / auth failure → a client error, surfaced as 400.
            raise ValueError(f"Could not connect to Snowflake: {e}")

        token = TokenSet(
            access_token=json.dumps(creds),
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token, AccountInfo(email=None, display_name=display_name)
