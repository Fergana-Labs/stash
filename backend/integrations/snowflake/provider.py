"""Snowflake api_key provider.

Snowflake is a SQL warehouse, exposed to the agent as a read-only *query*
source rather than a crawled document source. Credentials are pasted: a
**Programmatic Access Token** (a single token string — easiest, but needs a
network policy on the account) or **key-pair** auth as the alternative. Both
authenticate in place of a password (Snowflake is phasing out single-factor
passwords for service accounts). See client.py for the read-only query path and
integrations/base.py for the api_key contract.
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
        CredentialField(
            "account", "Account", placeholder="orgname-account_name",
            help="Your Snowflake account identifier (Admin → Accounts).",
        ),
        CredentialField("user", "User", placeholder="SVC_AGENT"),
        CredentialField(
            "token", "Programmatic Access Token", secret=True, optional=True,
            placeholder="Recommended — a single token string",
            help="Easiest: ALTER USER <u> ADD PROGRAMMATIC ACCESS TOKEN … (needs a network policy on the account).",
        ),
        CredentialField(
            "private_key", "Private Key (PEM)", secret=True, optional=True,
            placeholder="-----BEGIN PRIVATE KEY-----",
            help="Alternative to a token: key-pair auth.",
        ),
        CredentialField("private_key_passphrase", "Private Key Passphrase", secret=True, optional=True),
        CredentialField("warehouse", "Warehouse", optional=True, placeholder="COMPUTE_WH"),
        CredentialField("role", "Role", optional=True, placeholder="READ_ONLY"),
        CredentialField("database", "Database", optional=True, placeholder="(optional default)"),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        creds = {k: v.strip() for k, v in values.items() if v and v.strip()}
        if not creds.get("account") or not creds.get("user"):
            raise ValueError("Account and User are required")
        if not creds.get("token") and not creds.get("private_key") and not creds.get("password"):
            raise ValueError("Provide a Programmatic Access Token or a Private Key")

        try:
            display_name = await test_connection(creds)
        except ValueError:
            raise
        except Exception as e:
            # Connection / auth failure → a client error, surfaced as 400.
            raise ValueError("Could not connect to Snowflake; check credentials") from e

        token = TokenSet(
            access_token=json.dumps(creds),
            refresh_token=None,
            expires_at=None,
            scopes=[],
        )
        return token, AccountInfo(email=None, display_name=display_name)
