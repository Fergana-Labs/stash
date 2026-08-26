"""Workspace-scoped local model credentials: the console's Local model section.

What matters here:
- Only an operator of the workspace (X-Stash-Scope membership) can attach a
  local endpoint credential, and it lands on the workspace's login-less scope
  account — never on the caller's personal scope, which a bare headerless
  call must not reach.
- Validation and doc shape are the personal local flow's one shared helper:
  same 400s, same stored doc, so the resolver needs no change to run the
  workspace's agents (the developer-wiki curator) on PI against the endpoint.
- A non-activated scope 400s "activate first" — there is no silent write.
"""

import json
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from backend.config import settings
from backend.services import agent_auth, sprite_service, workspace_service
from backend.services import harness as h

from .conftest import unique_name
from .test_developer_platform import _developer
from .test_permissions import _auth, _register


@pytest.fixture(autouse=True)
def _fernet(monkeypatch):
    """Credential storage is Fernet-encrypted; CI has no INTEGRATIONS_ENCRYPTION_KEY."""
    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _scope_headers(api_key: str, scope_user_id: str) -> dict:
    return {**_auth(api_key), "X-Stash-Scope": scope_user_id}


async def _stored_doc(scope_user_id: str) -> dict | None:
    """The scope account's stored local credential doc (decrypted), or None."""
    cred = await agent_auth._get_credential(UUID(scope_user_id), "local")
    return json.loads(cred["secret"]) if cred is not None else None


async def _connect(
    client: AsyncClient,
    api_key: str,
    scope: str,
    model: str,
    base_url: str = "http://my-host:11434/v1",
    api_key_secret: str | None = None,
):
    return await client.post(
        "/api/v1/me/developer/agent-credentials",
        json={"base_url": base_url, "model": model, "api_key": api_key_secret},
        headers=_scope_headers(api_key, scope),
    )


# --- The happy path: connect / list / stored shape ---


@pytest.mark.asyncio
async def test_list_before_connect_is_empty(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    r = await client.get(
        "/api/v1/me/developer/agent-credentials",
        headers=_scope_headers(api_key, workspace["scope_user_id"]),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"connected": []}


@pytest.mark.asyncio
async def test_connect_keyless_stores_endpoint_doc(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    r = await _connect(client, api_key, scope, "llama3.1:8b")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "connected": ["local"]}

    r = await client.get(
        "/api/v1/me/developer/agent-credentials", headers=_scope_headers(api_key, scope)
    )
    assert r.json() == {"connected": ["local"]}
    # The stored doc is exactly the personal flow's shape — no key when keyless.
    assert await _stored_doc(scope) == {
        "base_url": "http://my-host:11434/v1",
        "model": "llama3.1:8b",
        "api_key": None,
    }


@pytest.mark.asyncio
async def test_connect_with_key_round_trips(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    r = await _connect(client, api_key, scope, "qwen2:7b", api_key_secret="ws-local-secret")
    assert r.status_code == 200, r.text
    doc = await _stored_doc(scope)
    assert doc == {
        "base_url": "http://my-host:11434/v1",
        "model": "qwen2:7b",
        "api_key": "ws-local-secret",
    }


# --- Validation: the personal flow's 400s, shared helper ---


@pytest.mark.asyncio
async def test_connect_rejects_bad_base_url(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    for bad_url in ("myhost:11434/v1", "ftp://h/v1"):
        r = await _connect(client, api_key, scope, "m", base_url=bad_url)
        assert r.status_code == 400, f"{bad_url!r} should be rejected: {r.text}"
        assert r.json()["detail"].startswith("base_url must be an absolute http(s) URL")
    # Rejection stores nothing.
    assert await _stored_doc(scope) is None


@pytest.mark.asyncio
async def test_connect_requires_model(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    r = await _connect(client, api_key, scope, "")
    assert r.status_code == 400
    assert r.json()["detail"] == "model is required for the local endpoint"
    assert await _stored_doc(scope) is None


# --- Disconnect + upsert ---


@pytest.mark.asyncio
async def test_disconnect_removes_credential(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    assert (await _connect(client, api_key, scope, "llama3.1:8b")).status_code == 200
    r = await client.delete(
        "/api/v1/me/developer/agent-credentials/local", headers=_scope_headers(api_key, scope)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "connected": []}
    assert await _stored_doc(scope) is None


@pytest.mark.asyncio
async def test_second_connect_upserts_one_row(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    assert (await _connect(client, api_key, scope, "model-a")).status_code == 200
    r = await _connect(client, api_key, scope, "model-b")
    assert r.status_code == 200, r.text
    assert (await _stored_doc(scope))["model"] == "model-b"
    row = await pool.fetchrow(
        "SELECT count(*) AS n FROM user_agent_credentials "
        "WHERE user_id = $1 AND provider = 'local'",
        UUID(scope),
    )
    assert row["n"] == 1


# --- Separation: personal and workspace scopes never mix ---


@pytest.mark.asyncio
async def test_personal_and_workspace_credentials_stay_separate(client: AsyncClient):
    personal_key, personal_body = await _register(client)
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]

    # The developer connects a personal endpoint; the workspace scope sees none.
    r = await client.post(
        "/api/v1/me/agent-credentials",
        json={
            "provider": "local",
            "base_url": "http://personal-host:11434/v1",
            "model": "personal-model",
        },
        headers=_auth(personal_key),
    )
    assert r.status_code == 200, r.text
    assert (
        await client.get(
            "/api/v1/me/developer/agent-credentials", headers=_scope_headers(api_key, scope)
        )
    ).json() == {"connected": []}
    assert await _stored_doc(scope) is None

    # The workspace connect leaves the personal endpoint untouched.
    r = await _connect(client, api_key, scope, "ws-model")
    assert r.status_code == 200, r.text
    assert (
        await client.get("/api/v1/me/agent-credentials", headers=_auth(personal_key))
    ).json() == {"connected": ["local"]}
    personal_doc = json.loads(
        (await agent_auth._get_credential(UUID(personal_body["id"]), "local"))["secret"]
    )
    assert personal_doc == {
        "base_url": "http://personal-host:11434/v1",
        "model": "personal-model",
        "api_key": None,
    }
    assert (await _stored_doc(scope))["model"] == "ws-model"


# --- Gates: membership, activation, no silent personal write ---


@pytest.mark.asyncio
async def test_stranger_cannot_touch_workspace_credentials(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = workspace["scope_user_id"]
    stranger_key, _ = await _register(client)
    headers = {**_auth(stranger_key), "X-Stash-Scope": scope}

    r = await client.get("/api/v1/me/developer/agent-credentials", headers=headers)
    assert r.status_code == 403
    r = await _connect(client, stranger_key, scope, "m")
    assert r.status_code == 403
    r = await client.delete("/api/v1/me/developer/agent-credentials/local", headers=headers)
    assert r.status_code == 403
    # Nothing leaked or was written.
    assert await _stored_doc(scope) is None


@pytest.mark.asyncio
async def test_inactive_scope_and_bare_personal_call_activate_first(client: AsyncClient):
    api_key, user_body, _ = await _developer(client)
    # A real workspace the developer created but never activated.
    workspace = await workspace_service.create_workspace(
        unique_name("inactive-ws"), None, created_by=UUID(user_body["id"])
    )
    scope = str(workspace["scope_user_id"])
    headers = _scope_headers(api_key, scope)

    r = await client.get("/api/v1/me/developer/agent-credentials", headers=headers)
    assert r.status_code == 400
    assert "activate first" in r.json()["detail"]
    r = await _connect(client, api_key, scope, "m")
    assert r.status_code == 400
    assert "activate first" in r.json()["detail"]
    assert await _stored_doc(scope) is None

    # No X-Stash-Scope at all: personal scope is not a developer workspace —
    # a 400, never a silent personal write.
    r = await client.get("/api/v1/me/developer/agent-credentials", headers=_auth(api_key))
    assert r.status_code == 400
    assert "activate first" in r.json()["detail"]
    r = await client.post(
        "/api/v1/me/developer/agent-credentials",
        json={"base_url": "http://my-host:11434/v1", "model": "m"},
        headers=_auth(api_key),
    )
    assert r.status_code == 400
    personal = await agent_auth._get_credential(UUID(user_body["id"]), "local")
    assert personal is None


# --- The outcome: the workspace's agents resolve to PI on the endpoint ---


@pytest.mark.asyncio
async def test_workspace_credential_resolves_to_pi(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    scope = UUID(workspace["scope_user_id"])

    # Before-state: a scope account with no credential runs the local exec
    # default (Claude) — what the developer-wiki curator was doing.
    auth = await agent_auth.resolve(scope)
    assert auth.harness is h.CLAUDE

    r = await _connect(client, api_key, str(scope), "llama3.1:8b")
    assert r.status_code == 200, r.text

    # Same resolve, no resolver change: PI on the workspace's endpoint, with
    # the pi models.json carrying the endpoint for the turn.
    auth = await agent_auth.resolve(scope)
    assert auth.harness is h.PI
    assert auth.endpoint == "http://my-host:11434/v1"
    assert auth.model == "llama3.1:8b"
    home = str(sprite_service.local_box_home())
    models = json.loads(auth.files[f"{home}/.pi/agent/models.json"])
    local = models["providers"]["local"]
    assert local["baseUrl"] == "http://my-host:11434/v1"
    assert local["api"] == "openai-completions"
    assert local["models"] == [{"id": "llama3.1:8b", "contextWindow": 131072, "maxTokens": 8192}]
