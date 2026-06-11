from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet

from .conftest import unique_name

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("gmail"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str) -> UUID:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("gmail_ws")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


async def _store_gmail(user_id: UUID, email: str, access_token: str) -> None:
    await storage.store_token(
        user_id,
        "gmail",
        TokenSet(
            access_token=access_token,
            refresh_token=f"refresh-{access_token}",
            expires_at=None,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        ),
        AccountInfo(email=email, display_name=email),
    )


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)


@pytest.mark.asyncio
async def test_gmail_tokens_are_keyed_by_mailbox(client: AsyncClient):
    _, user_id = await _register(client)

    await _store_gmail(user_id, "htdowling@gmail.com", "token-personal")
    await _store_gmail(user_id, "henry@joinstash.ai", "token-work")

    status = await storage.status(user_id, "gmail")

    assert status["connected"]
    assert {a["account_key"] for a in status["accounts"]} == {
        "htdowling@gmail.com",
        "henry@joinstash.ai",
    }
    assert (
        await storage.get_valid_token(user_id, "gmail", "htdowling@gmail.com") == "token-personal"
    )
    assert await storage.get_valid_token(user_id, "gmail", "henry@joinstash.ai") == "token-work"


@pytest.mark.asyncio
async def test_gmail_sources_target_specific_mailboxes(client: AsyncClient):
    api_key, user_id = await _register(client)
    workspace_id = await _create_workspace(client, api_key)
    await _store_gmail(user_id, "htdowling@gmail.com", "token-personal")
    await _store_gmail(user_id, "henry@joinstash.ai", "token-work")

    ambiguous = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={"source_type": "gmail"},
        headers=_auth(api_key),
    )
    assert ambiguous.status_code == 400
    assert ambiguous.json()["detail"] == "Choose a Gmail account to add."

    for email in ("htdowling@gmail.com", "henry@joinstash.ai"):
        added = await client.post(
            f"/api/v1/workspaces/{workspace_id}/sources",
            json={"source_type": "gmail", "external_ref": email},
            headers=_auth(api_key),
        )
        assert added.status_code == 200
        assert added.json()["external_ref"] == email
        assert added.json()["display_name"] == f"Gmail ({email})"

    listing = await client.get(f"/api/v1/workspaces/{workspace_id}/sources", headers=_auth(api_key))
    gmail_sources = [s for s in listing.json()["sources"] if s["type"] == "gmail"]

    assert {s["external_ref"] for s in gmail_sources} == {
        "htdowling@gmail.com",
        "henry@joinstash.ai",
    }
