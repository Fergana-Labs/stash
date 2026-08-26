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
    assert doc == {
        "base_url": "http://my-host:11434/v1",
        "model": "llama3.1:8b",
        "api_key": None,
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


async def _connect_local(
    client: AsyncClient,
    key: str,
    base_url: str = "http://tunnel.example/v1",
    model: str = "llama3.1:8b",
    api_key: str | None = None,
) -> None:
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={"provider": "local", "base_url": base_url, "model": model, "api_key": api_key},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text


MODELS_JSON_URL = "/api/v1/me/agent-credentials/local/models-json"

# 4-space indent + reordered keys + a second model: non-default formatting so
# the round-trip proves the stored text is kept byte-for-byte (no re-serialize).
CUSTOM_MODELS_JSON = """{
    "providers": {
        "local": {
            "api": "openai-completions",
            "baseUrl": "http://tunnel.example/v1",
            "apiKey": "$STASH_LOCAL_KEY",
            "models": [
                {"id": "llama3.1:8b", "maxTokens": 4096, "contextWindow": 32768},
                {"id": "qwen2:7b", "maxTokens": 8192, "contextWindow": 65536}
            ],
            "compat": {"supportsDeveloperRole": false, "supportsReasoningEffort": false}
        }
    }
}
"""


@pytest.mark.asyncio
async def test_get_local_models_json_default(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "my-secret-key")
    r = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] is False
    local = json.loads(body["models_json"])["providers"]["local"]
    assert local["baseUrl"] == "http://tunnel.example/v1"
    assert local["api"] == "openai-completions"
    assert local["apiKey"] == "$STASH_LOCAL_KEY"
    assert local["compat"] == {"supportsDeveloperRole": False, "supportsReasoningEffort": False}
    assert local["models"] == [{"id": "llama3.1:8b", "contextWindow": 131072, "maxTokens": 8192}]


@pytest.mark.asyncio
async def test_get_local_models_json_default_keyless(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key, "http://host:11434/v1", "qwen2:7b", None)
    r = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert r.status_code == 200, r.text
    assert r.json()["stored"] is False
    local = json.loads(r.json()["models_json"])["providers"]["local"]
    assert local["apiKey"] == "local"  # keyless endpoints get the literal dummy


@pytest.mark.asyncio
async def test_get_local_models_json_matches_synthesized_turn_file(client: AsyncClient):
    """Proof of a single synthesis path: the GET'd default and the file the
    turn actually writes are produced by the same helper — byte-identical."""
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "my-secret-key")
    user_id = (await client.get("/api/v1/users/me", headers=_auth(key))).json()["id"]
    cred = await agent_auth._get_credential(UUID(user_id), "local")
    turn_file = agent_auth._local_auth(cred).files["/home/sprite/.pi/agent/models.json"]
    r = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert r.json()["models_json"] == turn_file


@pytest.mark.asyncio
async def test_get_local_models_json_404_not_connected(client: AsyncClient):
    key = await _register(client)
    r = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert r.status_code == 404
    assert r.json()["detail"] == "local endpoint is not connected"


@pytest.mark.asyncio
async def test_put_local_models_json_roundtrip_verbatim(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key)
    r = await client.put(
        MODELS_JSON_URL, json={"models_json": CUSTOM_MODELS_JSON}, headers=_auth(key)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "stored": True}
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.json() == {"models_json": CUSTOM_MODELS_JSON, "stored": True}


@pytest.mark.asyncio
async def test_put_rejects_unparseable(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key)
    r = await client.put(MODELS_JSON_URL, json={"models_json": "{"}, headers=_auth(key))
    assert r.status_code == 400
    assert "not valid JSON" in r.json()["detail"]
    # The failed save leaves the previous (absent) value untouched.
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.json()["stored"] is False


@pytest.mark.asyncio
async def test_put_requires_providers_object(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key)
    for bad in ('{"foo": 1}', "[1, 2]", '{"providers": []}'):  # noqa: S108
        r = await client.put(MODELS_JSON_URL, json={"models_json": bad}, headers=_auth(key))
        assert r.status_code == 400, f"{bad!r} should be rejected: {r.text}"
        assert "providers" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_404_not_connected(client: AsyncClient):
    key = await _register(client)
    r = await client.put(
        MODELS_JSON_URL, json={"models_json": '{"providers": {}}'}, headers=_auth(key)
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "local endpoint is not connected"


@pytest.mark.asyncio
async def test_put_replaces_previous_override(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key)
    override_a = '{"providers": {"a": {"models": []}}}'
    override_b = '{"providers": {"b": {"models": []}}}'
    assert (
        await client.put(MODELS_JSON_URL, json={"models_json": override_a}, headers=_auth(key))
    ).status_code == 200
    assert (
        await client.put(MODELS_JSON_URL, json={"models_json": override_b}, headers=_auth(key))
    ).status_code == 200
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.json() == {"models_json": override_b, "stored": True}


@pytest.mark.asyncio
async def test_reset_returns_to_synthesized_default(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "my-secret-key")
    await client.put(MODELS_JSON_URL, json={"models_json": CUSTOM_MODELS_JSON}, headers=_auth(key))
    r = await client.delete(MODELS_JSON_URL, headers=_auth(key))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "stored": False}
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.json()["stored"] is False
    local = json.loads(g.json()["models_json"])["providers"]["local"]
    assert local["apiKey"] == "$STASH_LOCAL_KEY"
    assert local["models"] == [{"id": "llama3.1:8b", "contextWindow": 131072, "maxTokens": 8192}]


@pytest.mark.asyncio
async def test_reset_404_not_connected(client: AsyncClient):
    key = await _register(client)
    r = await client.delete(MODELS_JSON_URL, headers=_auth(key))
    assert r.status_code == 404
    assert r.json()["detail"] == "local endpoint is not connected"


@pytest.mark.asyncio
async def test_disconnect_clears_override(client: AsyncClient):
    """Disconnecting the local endpoint deletes the row — override with it —
    so a later GET is 404, not a stale override."""
    key = await _register(client)
    await _connect_local(client, key)
    await client.put(MODELS_JSON_URL, json={"models_json": CUSTOM_MODELS_JSON}, headers=_auth(key))
    d = await client.delete("/api/v1/me/agent-credentials/local", headers=_auth(key))
    assert d.status_code == 200
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.status_code == 404


@pytest.mark.asyncio
async def test_reconnect_preserves_override(client: AsyncClient):
    """The store_credential upsert must not touch the override: reconnecting
    with a different model/key keeps the user's models.json."""
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "my-secret-key")
    await client.put(MODELS_JSON_URL, json={"models_json": CUSTOM_MODELS_JSON}, headers=_auth(key))
    await _connect_local(client, key, "http://other.example/v1", "qwen2:7b", None)
    g = await client.get(MODELS_JSON_URL, headers=_auth(key))
    assert g.json() == {"models_json": CUSTOM_MODELS_JSON, "stored": True}
