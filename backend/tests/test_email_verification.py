"""Email-a-link verification — the path for password signups to reach
`email_verified = true`, the trust anchor for derived workspace membership.
Without it a password account can never join its domain workspace."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, email: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1", "email": email},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body["id"]


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def _stored_token(pool, user_id: str) -> str | None:
    return await pool.fetchval("SELECT token FROM email_verifications WHERE user_id = $1", user_id)


@pytest.mark.asyncio
async def test_register_issues_token_and_confirm_verifies(client: AsyncClient, pool):
    _key, user_id = await _register(client, f"{unique_name()}@example.com")

    token = await _stored_token(pool, user_id)
    assert token

    resp = await client.post("/api/v1/users/verify-email", json={"token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"verified": True}
    assert await pool.fetchval("SELECT email_verified FROM users WHERE id = $1", user_id)

    # Single-use: the same token is gone after consumption.
    resp = await client.post("/api/v1/users/verify-email", json={"token": token})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resend_replaces_token(client: AsyncClient, pool):
    key, user_id = await _register(client, f"{unique_name()}@example.com")
    first = await _stored_token(pool, user_id)

    resp = await client.post("/api/v1/users/me/verify-email", headers=_auth(key))
    assert resp.status_code == 202, resp.text
    assert resp.json()["sent_to"].endswith("@example.com")

    second = await _stored_token(pool, user_id)
    assert second and second != first

    # The replaced token is dead; the fresh one works.
    assert (
        await client.post("/api/v1/users/verify-email", json={"token": first})
    ).status_code == 400
    assert (
        await client.post("/api/v1/users/verify-email", json={"token": second})
    ).status_code == 200


@pytest.mark.asyncio
async def test_resend_rejects_already_verified(client: AsyncClient, pool):
    key, user_id = await _register(client, f"{unique_name()}@example.com")
    await pool.execute("UPDATE users SET email_verified = true WHERE id = $1", user_id)

    resp = await client.post("/api/v1/users/me/verify-email", headers=_auth(key))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_token_for_changed_email_does_not_verify(client: AsyncClient, pool):
    """A token proves control of the address it was mailed to. If the account's
    email changed since, consuming the token must not verify the new address."""
    _key, user_id = await _register(client, f"{unique_name()}@example.com")
    token = await _stored_token(pool, user_id)

    await pool.execute(
        "UPDATE users SET email = $2 WHERE id = $1", user_id, f"{unique_name()}@other.com"
    )

    resp = await client.post("/api/v1/users/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert not await pool.fetchval("SELECT email_verified FROM users WHERE id = $1", user_id)
