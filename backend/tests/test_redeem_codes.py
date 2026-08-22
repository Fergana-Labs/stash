"""Redeemable access codes (hackathons).

The contract: a valid code grants its plan exactly once per account, uses are
consumed atomically against max_uses, and invalid/exhausted codes fail loud
with distinct statuses so the UI can say why.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email


async def _user(client: AsyncClient) -> tuple[str, dict]:
    return await _register_with_email(client, f"{unique_name('hacker')}@example.com")


async def _mint(pool, code: str, plan: str = "enterprise", max_uses: int | None = None) -> None:
    await pool.execute(
        "INSERT INTO redeem_codes (code, plan, max_uses) VALUES ($1, $2, $3)",
        code,
        plan,
        max_uses,
    )


@pytest.mark.asyncio
async def test_redeem_grants_the_plan_once(client: AsyncClient, pool):
    key, body = await _user(client)
    await _mint(pool, "hack26", max_uses=2)

    # Case and whitespace are the user's problem to not have.
    resp = await client.post(
        "/api/v1/users/me/redeem-code", json={"code": "  HACK26 "}, headers=_auth(key)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "enterprise"
    row = await pool.fetchrow(
        "SELECT plan, redeemed_code FROM users WHERE id = $1", UUID(body["id"])
    )
    assert row["plan"] == "enterprise"
    assert row["redeemed_code"] == "hack26"

    # An account only gets one code — the second attempt doesn't burn a use.
    resp = await client.post(
        "/api/v1/users/me/redeem-code", json={"code": "hack26"}, headers=_auth(key)
    )
    assert resp.status_code == 409
    assert await pool.fetchval("SELECT use_count FROM redeem_codes WHERE code = 'hack26'") == 1


@pytest.mark.asyncio
async def test_unknown_code_is_404(client: AsyncClient):
    key, _ = await _user(client)
    resp = await client.post(
        "/api/v1/users/me/redeem-code", json={"code": "nope"}, headers=_auth(key)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_exhausted_code_is_410(client: AsyncClient, pool):
    key, _ = await _user(client)
    await _mint(pool, "tiny", max_uses=1)
    await pool.execute("UPDATE redeem_codes SET use_count = 1 WHERE code = 'tiny'")
    resp = await client.post(
        "/api/v1/users/me/redeem-code", json={"code": "tiny"}, headers=_auth(key)
    )
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_expired_code_is_410(client: AsyncClient, pool):
    key, _ = await _user(client)
    await pool.execute(
        "INSERT INTO redeem_codes (code, plan, expires_at) "
        "VALUES ('old', 'enterprise', now() - interval '1 hour')"
    )
    resp = await client.post(
        "/api/v1/users/me/redeem-code", json={"code": "old"}, headers=_auth(key)
    )
    assert resp.status_code == 410
