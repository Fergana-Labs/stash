"""The account status a client polls to see an OAuth consent complete.

`stash sources connect` opens the provider's consent screen and then watches
this endpoint to know the grant landed. A brand-new account is easy to spot —
a key appears. Repairing an expired grant is not: the row keeps its
account_key, so the only evidence the consent succeeded is that store_token
rewrote updated_at. If that field stops being exposed, the CLI cannot tell a
finished reconnect from an abandoned one and waits out its whole timeout on a
consent the user actually completed.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet

from .conftest import unique_name

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("gmail"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


async def _authorize(user_id: UUID, email: str) -> None:
    """A completed consent for one mailbox. The token is deliberately unexpired
    so reading status never attempts a refresh over the network."""
    await storage.store_token(
        user_id,
        "gmail",
        TokenSet(
            access_token=f"token-{email}",
            refresh_token=f"refresh-{email}",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        ),
        AccountInfo(email=email, display_name="Henry"),
    )


async def _accounts(client: AsyncClient, api_key: str) -> list[dict]:
    resp = await client.get(
        "/api/v1/integrations/gmail/status", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert resp.status_code == 200
    return resp.json()["accounts"]


@pytest.mark.asyncio
async def test_status_moves_updated_at_when_an_account_is_reauthorized(client: AsyncClient):
    api_key, user_id = await _register(client)
    await _authorize(user_id, "henry@ferganalabs.com")

    before = await _accounts(client, api_key)
    assert [a["account_key"] for a in before] == ["henry@ferganalabs.com"]
    assert before[0]["updated_at"] is not None

    await asyncio.sleep(0.01)
    await _authorize(user_id, "henry@ferganalabs.com")
    after = await _accounts(client, api_key)

    # Same mailbox, same key — only the timestamp separates the repaired grant
    # from the dead one it replaced.
    assert [a["account_key"] for a in after] == ["henry@ferganalabs.com"]
    assert after[0]["updated_at"] > before[0]["updated_at"]


@pytest.mark.asyncio
async def test_status_lists_a_second_mailbox_separately(client: AsyncClient):
    """Gmail holds several accounts, so authorizing a personal mailbox must add
    a row rather than overwrite the work one — otherwise connecting the second
    account would silently cost the user the first."""
    api_key, user_id = await _register(client)
    await _authorize(user_id, "henry@ferganalabs.com")
    await _authorize(user_id, "htdowling@gmail.com")

    accounts = await _accounts(client, api_key)

    assert sorted(a["account_key"] for a in accounts) == [
        "henry@ferganalabs.com",
        "htdowling@gmail.com",
    ]
    assert all(a["disconnected"] is False for a in accounts)
