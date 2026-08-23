"""Connect / list / disconnect the cloud agent's model credential.

The local endpoint flow is new: the credential is a base URL + model doc
(never an sk- key), and the resolver sees it as kind "endpoint".
"""

import json
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from backend.config import settings
from backend.services import agent_auth

from .conftest import unique_name


@pytest.fixture(autouse=True)
def _fernet(monkeypatch):
    """Credential storage is Fernet-encrypted; CI has no INTEGRATIONS_ENCRYPTION_KEY."""
    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())


async def _register(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("cred"), "password": "securepassword1"},
    )
    return r.json()["api_key"]


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


async def _stored_secret(client: AsyncClient, key: str, provider: str) -> str:
    """The credential secret the connect endpoint persisted for this provider
    (a JSON doc for local, the bare key for the key providers)."""
    user_id = (await client.get("/api/v1/users/me", headers=_auth(key))).json()["id"]
    cred = await agent_auth._get_credential(UUID(user_id), provider)
    assert cred is not None
    return cred["secret"]


@pytest.mark.asyncio
async def test_connect_local_without_key(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "local", "base_url": "http://my-host:11434/v1", "model": "llama3.1:8b"},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    assert "local" in r.json()["connected"]
    doc = json.loads(await _stored_secret(client, key, "local"))
    # Size fields are absent from the request → stored as null (the documented
    # constants resolve at auth time, not connect time).
    assert doc == {
        "base_url": "http://my-host:11434/v1",
        "model": "llama3.1:8b",
        "api_key": None,
        "context_window": None,
        "max_tokens": None,
    }


@pytest.mark.asyncio
async def test_connect_local_with_key_stores_it(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={
            "provider": "local",
            "base_url": "https://tunnel.example/v1",
            "model": "qwen2:7b",
            "api_key": "my-local-secret",
        },
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    doc = json.loads(await _stored_secret(client, key, "local"))
    assert doc["api_key"] == "my-local-secret"


@pytest.mark.asyncio
async def test_connect_local_rejects_relative_or_bad_scheme_url(client: AsyncClient):
    key = await _register(client)
    for bad_url in ("my-host:11434/v1", "ftp://host/v1", "://nope", ""):
        r = await client.post(
            "/api/v1/me/agent-credentials",
            json={"provider": "local", "base_url": bad_url, "model": "m"},
            headers=_auth(key),
        )
        assert r.status_code == 400, f"{bad_url!r} should be rejected: {r.text}"
        assert "base_url" in r.json()["detail"]


@pytest.mark.asyncio
async def test_connect_local_requires_model(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "local", "base_url": "http://host:11434/v1", "model": "  "},
        headers=_auth(key),
    )
    assert r.status_code == 400
    assert "model" in r.json()["detail"]


@pytest.mark.asyncio
async def test_connect_local_with_custom_sizes_stores_them(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={
            "provider": "local",
            "base_url": "http://my-host:11434/v1",
            "model": "llama3.1:8b",
            "context_window": 32768,
            "max_tokens": 4096,
        },
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    assert "local" in r.json()["connected"]
    doc = json.loads(await _stored_secret(client, key, "local"))
    assert doc["context_window"] == 32768
    assert doc["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_connect_local_rejects_non_positive_sizes(client: AsyncClient):
    key = await _register(client)
    for bad in (
        {"context_window": 0},
        {"context_window": -1},
        {"max_tokens": 0},
        {"max_tokens": -5},
    ):
        r = await client.post(
            "/api/v1/me/agent-credentials",
            json={"provider": "local", "base_url": "http://host:11434/v1", "model": "m", **bad},
            headers=_auth(key),
        )
        assert r.status_code == 400, f"{bad} should be rejected: {r.text}"
        assert r.json()["detail"] == "context_window and max_tokens must be positive integers"


@pytest.mark.asyncio
async def test_connect_local_rejects_output_budget_not_fitting_context(client: AsyncClient):
    key = await _register(client)
    # The effective pair (provided value, else the documented constant) must
    # keep the output budget strictly inside the context window.
    cases = (
        (
            {"context_window": 8192, "max_tokens": 8192},
            "max_tokens (8192) must be less than context_window (8192)",
        ),
        (
            {"context_window": 4096, "max_tokens": 8192},
            "max_tokens (8192) must be less than context_window (4096)",
        ),
        # context_window only: the 8192 default output budget doesn't fit 4096.
        ({"context_window": 4096}, "max_tokens (8192) must be less than context_window (4096)"),
        # max_tokens only: 200000 is above the 131072 default context window.
        ({"max_tokens": 200000}, "max_tokens (200000) must be less than context_window (131072)"),
    )
    for extra, needle in cases:
        r = await client.post(
            "/api/v1/me/agent-credentials",
            json={"provider": "local", "base_url": "http://host:11434/v1", "model": "m", **extra},
            headers=_auth(key),
        )
        assert r.status_code == 400, f"{extra} should be rejected: {r.text}"
        assert needle in r.json()["detail"]


@pytest.mark.asyncio
async def test_connect_local_rejects_non_integer_size(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={
            "provider": "local",
            "base_url": "http://host:11434/v1",
            "model": "m",
            "context_window": "wide",
        },
        headers=_auth(key),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_connect_anthropic_key_regression(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "anthropic", "api_key": "sk-ant-mine"},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    assert "anthropic" in r.json()["connected"]
    # Key providers store the bare key, not a doc.
    assert await _stored_secret(client, key, "anthropic") == "sk-ant-mine"


@pytest.mark.asyncio
async def test_connect_anthropic_without_key_rejected(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials", json={"provider": "anthropic"}, headers=_auth(key)
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "api_key is required"


@pytest.mark.asyncio
async def test_connect_unknown_provider_rejected(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "bogus", "api_key": "x"},
        headers=_auth(key),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_oauth_start_local_rejected(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        "/api/v1/me/agent-credentials/oauth/start",
        json={"provider": "local"},
        headers=_auth(key),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_disconnect_local(client: AsyncClient):
    key = await _register(client)
    await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "local", "base_url": "http://host:11434/v1", "model": "m"},
        headers=_auth(key),
    )
    r = await client.delete("/api/v1/me/agent-credentials/local", headers=_auth(key))
    assert r.status_code == 200
    assert "local" not in r.json()["connected"]
