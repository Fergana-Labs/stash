"""Connect / list / disconnect the cloud agent's model credential.

The local endpoint flow is new: the credential is a base URL + model doc
(never an sk- key), and the resolver sees it as kind "endpoint".
"""

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


# ── The list endpoint also carries the local doc ────────────────────────────
# Reconnecting must not ask the user to retype a base URL and model id, and the
# connected row must be able to show the user their own key. The local doc is
# the ONLY credential the API ever returns: it is the user's own endpoint
# config, while the key providers' secrets stay opaque.

LIST_URL = "/api/v1/me/agent-credentials"


@pytest.mark.asyncio
async def test_list_returns_local_doc_including_its_key(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "sk-local-abcdef")
    r = await client.get(LIST_URL, headers=_auth(key))
    assert r.status_code == 200, r.text
    assert r.json()["connected"] == ["local"]
    assert r.json()["local"] == {
        "base_url": "http://tunnel.example/v1",
        "model": "llama3.1:8b",
        "api_key": "sk-local-abcdef",
    }


@pytest.mark.asyncio
async def test_list_returns_local_doc_keyless(client: AsyncClient):
    key = await _register(client)
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b")
    r = await client.get(LIST_URL, headers=_auth(key))
    assert r.json()["local"] == {
        "base_url": "http://tunnel.example/v1",
        "model": "llama3.1:8b",
        "api_key": None,
    }


@pytest.mark.asyncio
async def test_list_local_is_null_when_nothing_connected(client: AsyncClient):
    key = await _register(client)
    r = await client.get(LIST_URL, headers=_auth(key))
    assert r.json() == {"connected": [], "local": None}


@pytest.mark.asyncio
async def test_list_keeps_key_provider_secrets_out_of_the_response(client: AsyncClient):
    """The local key is the user's own endpoint config and may come back; a
    Claude/OpenRouter key must never appear anywhere in the payload."""
    key = await _register(client)
    await client.post(
        LIST_URL, json={"provider": "anthropic", "api_key": "sk-ant-leaked"}, headers=_auth(key)
    )
    await client.post(
        LIST_URL, json={"provider": "openrouter", "api_key": "sk-or-leaked"}, headers=_auth(key)
    )
    await _connect_local(client, key, "http://tunnel.example/v1", "llama3.1:8b", "sk-local-abcdef")
    r = await client.get(LIST_URL, headers=_auth(key))
    assert "sk-ant-leaked" not in r.text
    assert "sk-or-leaked" not in r.text
    assert r.json()["local"]["api_key"] == "sk-local-abcdef"


# ── Test connection: the backend dials the endpoint on demand ───────────────
# The sprite-side preflight only proves reachability, one turn too late. These
# tests run the probe against a real local HTTP server so each response shape —
# and the request the probe itself sends — is observed, not mocked.

TEST_URL = "/api/v1/me/agent-credentials/local/test"


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        server: _ProbeEndpoint = self.server
        server.requests.append((self.path, self.headers.get("Authorization")))
        if server.mode == "unauthorized":
            self._respond(
                401,
                b'{"error": {"message": "token_not_found_in_db: no token with that hash"}}',
                "application/json",
            )
        elif server.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "https://login.example/oidc")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif server.mode == "bad_shape":
            self._respond(200, b"<html><body>proxy says hi</body></html>", "text/html")
        else:
            if server.mode == "slow":
                time.sleep(2)
            self._respond(
                200,
                b'{"object": "list", "data": [{"id": "mock-model-1"}, {"id": "mock-model-2"}]}',
                "application/json",
            )

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        """Silence the per-request stderr the default handler writes."""


class _ProbeEndpoint(ThreadingHTTPServer):
    """A stand-in OpenAI-compatible provider on a free loopback port."""

    mode: str
    requests: list[tuple[str, str | None]]

    def __init__(self, mode: str):
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.mode = mode
        self.requests = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"


@pytest.fixture
def probe_endpoints() -> Iterator[Callable[[str], _ProbeEndpoint]]:
    servers: list[_ProbeEndpoint] = []

    def start(mode: str) -> _ProbeEndpoint:
        server = _ProbeEndpoint(mode)
        servers.append(server)
        return server

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


def _refused_base_url() -> str:
    """A port that was bound and released, so connecting is refused outright."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/v1"


@pytest.mark.asyncio
async def test_local_test_lists_models_and_sends_the_key(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    endpoint = probe_endpoints("ok")
    key = await _register(client)
    r = await client.post(
        TEST_URL,
        json={"base_url": endpoint.base_url, "model": "mock-model-1", "api_key": "sk-local"},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "ok": True,
        "http_status": 200,
        "models": ["mock-model-1", "mock-model-2"],
    }
    # The probe dials the endpoint's own listing with the candidate key attached.
    assert endpoint.requests == [("/v1/models", "Bearer sk-local")]


@pytest.mark.asyncio
async def test_local_test_omits_the_header_when_keyless(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    endpoint = probe_endpoints("ok")
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": endpoint.base_url, "model": "mock-model-1"}, headers=_auth(key)
    )
    assert r.json()["ok"] is True
    assert endpoint.requests == [("/v1/models", None)]


@pytest.mark.asyncio
async def test_local_test_surfaces_the_provider_error_body(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    """The point of the route: a wrong key is reported as the provider said it
    (LiteLLM's token_not_found_in_db), not as a generic failure."""
    endpoint = probe_endpoints("unauthorized")
    key = await _register(client)
    r = await client.post(
        TEST_URL,
        json={"base_url": endpoint.base_url, "model": "mock-model-1", "api_key": "sk-wrong"},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["http_status"] == 401
    assert "token_not_found_in_db" in body["error_detail"]


@pytest.mark.asyncio
async def test_local_test_flags_a_redirect_instead_of_following_it(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    endpoint = probe_endpoints("redirect")
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": endpoint.base_url, "model": "mock-model-1"}, headers=_auth(key)
    )
    body = r.json()
    assert body["ok"] is False
    assert body["http_status"] == 302
    assert "https://login.example/oidc" in body["error_detail"]


@pytest.mark.asyncio
async def test_local_test_flags_a_success_that_is_not_a_model_list(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    """A 200 from a proxy page is not a working model endpoint."""
    endpoint = probe_endpoints("bad_shape")
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": endpoint.base_url, "model": "mock-model-1"}, headers=_auth(key)
    )
    body = r.json()
    assert body["ok"] is False
    assert body["http_status"] == 200
    assert "models" not in body
    assert "proxy says hi" in body["error_detail"]


@pytest.mark.asyncio
async def test_local_test_reports_connection_refused(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        TEST_URL,
        json={"base_url": _refused_base_url(), "model": "mock-model-1"},
        headers=_auth(key),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["http_status"] is None
    assert body["error_detail"].startswith("connection failed")


@pytest.mark.asyncio
async def test_local_test_reports_timeout(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    probe_endpoints: Callable[[str], _ProbeEndpoint],
):
    monkeypatch.setattr(agent_auth, "LOCAL_PROBE_TIMEOUT_S", 0.3)
    endpoint = probe_endpoints("slow")
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": endpoint.base_url, "model": "mock-model-1"}, headers=_auth(key)
    )
    body = r.json()
    assert body["ok"] is False
    assert body["http_status"] is None
    assert body["error_detail"] == "timed out after 0.3s"


@pytest.mark.asyncio
async def test_local_test_validates_before_dialing(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    """An unusable base URL is rejected with connect's own message, and nothing
    is dialed — the probe cannot be used to spray a host the form should refuse."""
    endpoint = probe_endpoints("ok")
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": "my-host:11434/v1", "model": "mock-model-1"}, headers=_auth(key)
    )
    assert r.status_code == 400
    assert r.json()["detail"] == agent_auth.LOCAL_BASE_URL_HINT
    assert endpoint.requests == []


@pytest.mark.asyncio
async def test_local_test_requires_model(client: AsyncClient):
    key = await _register(client)
    r = await client.post(
        TEST_URL, json={"base_url": "http://127.0.0.1:9/v1", "model": "  "}, headers=_auth(key)
    )
    assert r.status_code == 400
    assert "model" in r.json()["detail"]


@pytest.mark.asyncio
async def test_local_test_requires_auth(client: AsyncClient):
    r = await client.post(TEST_URL, json={"base_url": "http://127.0.0.1:9/v1", "model": "m"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_local_test_is_a_pure_probe(
    client: AsyncClient, probe_endpoints: Callable[[str], _ProbeEndpoint]
):
    """It tests exactly the values sent: a stored credential is neither read as
    the default nor overwritten by the attempt."""
    endpoint = probe_endpoints("ok")
    key = await _register(client)
    await _connect_local(client, key, "http://stored.example/v1", "stored-model", "stored-key")
    r = await client.post(
        TEST_URL,
        json={"base_url": endpoint.base_url, "model": "mock-model-1", "api_key": "candidate"},
        headers=_auth(key),
    )
    assert r.json()["ok"] is True
    assert json.loads(await _stored_secret(client, key, "local")) == {
        "base_url": "http://stored.example/v1",
        "model": "stored-model",
        "api_key": "stored-key",
    }
