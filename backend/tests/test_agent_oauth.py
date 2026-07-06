"""OAuth connect flows for Claude/Codex: URL construction, state, exchange."""

import json
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.services import agent_auth, agent_oauth


def test_claude_authorize_url_shape():
    uid = uuid.uuid4()
    out = agent_oauth.start(uid, "anthropic")
    url = out["authorize_url"]
    assert url.startswith("https://claude.com/cai/oauth/authorize?")
    q = parse_qs(urlparse(url).query)
    assert q["client_id"][0] == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    assert q["code"][0] == "true"  # Claude-specific leading param
    assert q["code_challenge_method"][0] == "S256"
    assert q["redirect_uri"][0] == "https://platform.claude.com/oauth/code/callback"
    assert "user:inference" in q["scope"][0]
    # state round-trips to the right user + provider + a verifier.
    payload = agent_oauth._decode_state(out["state"])
    assert payload["u"] == str(uid) and payload["p"] == "anthropic" and payload["v"]


def test_codex_authorize_url_shape():
    out = agent_oauth.start(uuid.uuid4(), "openai")
    q = parse_qs(urlparse(out["authorize_url"]).query)
    assert q["client_id"][0] == "app_EMoamEEZ73f0CkXaXp7hrann"
    assert q["codex_cli_simplified_flow"][0] == "true"
    assert q["redirect_uri"][0] == "http://localhost:1455/auth/callback"


def test_pkce_challenge_is_s256_of_verifier():
    import base64
    import hashlib

    verifier, challenge = agent_oauth._pkce()
    expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == expect


def test_parse_pasted_code_variants():
    assert agent_oauth._parse_pasted_code("abc") == ("abc", None)
    assert agent_oauth._parse_pasted_code("abc#xyz") == ("abc", "xyz")
    code, state = agent_oauth._parse_pasted_code("http://localhost:1455/auth/callback?code=C&state=S")
    assert code == "C" and state == "S"


def test_unknown_provider_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        agent_oauth.get("openrouter")  # OpenRouter has no OAuth


def test_claude_credential_blob_shape():
    blob = agent_oauth._credential_blob(
        agent_oauth.CLAUDE,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "a b"},
    )
    parsed = json.loads(blob)["claudeAiOauth"]
    assert parsed["accessToken"] == "at" and parsed["refreshToken"] == "rt"
    assert parsed["scopes"] == ["a", "b"] and parsed["subscriptionType"] == "max"
    assert parsed["expiresAt"] > 0
    # agent_auth materializes this verbatim into ~/.claude/.credentials.json.
    run = agent_auth._byo_auth({"provider": "anthropic", "kind": "oauth", "secret": blob})
    assert "/home/sprite/.claude/.credentials.json" in run.files
    assert run.env["CLAUDE_CONFIG_DIR"] == "/home/sprite/.claude"


def test_codex_credential_blob_wraps_into_auth_json():
    blob = agent_oauth._credential_blob(
        agent_oauth.CODEX,
        {"access_token": "at", "id_token": None, "refresh_token": "rt"},
    )
    # agent_auth wraps a bare token set into a proper auth.json (adds `tokens`).
    run = agent_auth._byo_auth({"provider": "openai", "kind": "oauth", "secret": blob})
    auth_json = json.loads(next(iter(run.files.values())))
    assert auth_json["OPENAI_API_KEY"] is None
    assert auth_json["tokens"]["access_token"] == "at"
    assert "last_refresh" in auth_json


@pytest.mark.asyncio
async def test_finish_exchanges_and_stores(monkeypatch):
    uid = uuid.uuid4()
    started = agent_oauth.start(uid, "anthropic")
    state = started["state"]

    async def fake_post(self, url, json=None, **kw):
        assert json["grant_type"] == "authorization_code"
        assert json["code"] == "THECODE"
        assert json["code_verifier"]  # the PKCE verifier from state
        return httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    stored = {}

    async def fake_store(user_id, provider, kind, secret):
        stored.update(user_id=user_id, provider=provider, kind=kind, secret=secret)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(agent_auth, "store_credential", fake_store)

    await agent_oauth.finish(uid, "anthropic", "THECODE", state)
    assert stored["provider"] == "anthropic" and stored["kind"] == "oauth"
    assert json.loads(stored["secret"])["claudeAiOauth"]["accessToken"] == "AT"


@pytest.mark.asyncio
async def test_finish_rejects_mismatched_state(monkeypatch):
    from fastapi import HTTPException

    other = agent_oauth.start(uuid.uuid4(), "anthropic")["state"]
    with pytest.raises(HTTPException):
        await agent_oauth.finish(uuid.uuid4(), "anthropic", "code", other)
