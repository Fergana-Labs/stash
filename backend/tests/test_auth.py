"""Tests for user registration, login, and API key authentication."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    name = unique_name()
    resp = await client.post("/api/v1/users/register", json={
        "name": name, "password": "securepassword1",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == name
    assert body["api_key"].startswith("mc_")


@pytest.mark.asyncio
async def test_register_duplicate_name(client: AsyncClient):
    name = unique_name()
    payload = {"name": name, "password": "securepassword1"}
    await client.post("/api/v1/users/register", json=payload)
    resp = await client.post("/api/v1/users/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient):
    resp = await client.post("/api/v1/users/register", json={
        "name": unique_name(), "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    name = unique_name()
    password = "correctpassword1"
    reg = await client.post("/api/v1/users/register", json={
        "name": name, "password": password,
    })
    assert reg.status_code == 201

    login = await client.post("/api/v1/users/login", json={"name": name, "password": password})
    assert login.status_code == 200
    assert login.json()["api_key"].startswith("mc_")


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    name = unique_name()
    await client.post("/api/v1/users/register", json={
        "name": name, "password": "correctpassword1",
    })
    resp = await client.post("/api/v1/users/login", json={"name": name, "password": "wrongpassword"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_auth(client: AsyncClient):
    name = unique_name()
    reg = await client.post("/api/v1/users/register", json={
        "name": name, "password": "securepassword1",
    })
    api_key = reg.json()["api_key"]

    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {api_key}"})
    assert me.status_code == 200
    assert me.json()["name"] == name


@pytest.mark.asyncio
async def test_invalid_api_key_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer mc_fakekeyxxxx"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 403
