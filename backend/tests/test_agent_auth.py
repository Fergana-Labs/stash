"""Per-user harness + credential resolution: BYO keys, managed OpenRouter, gate."""

import uuid

import pytest

from backend.config import settings
from backend.services import agent_auth, billing_service
from backend.services import harness as h


@pytest.mark.asyncio
async def test_local_mode_uses_claude_no_injection(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.CLAUDE and auth.env == {} and auth.files == {}


@pytest.mark.asyncio
async def test_byo_anthropic_key_runs_claude(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def cred(_uid):
        return {"provider": "anthropic", "kind": "api_key", "secret": "sk-ant-mine"}

    monkeypatch.setattr(agent_auth, "_get_credential", cred)
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.CLAUDE
    assert auth.env == {"ANTHROPIC_API_KEY": "sk-ant-mine"} and auth.files == {}


@pytest.mark.asyncio
async def test_byo_openai_key_runs_codex(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def cred(_uid):
        return {"provider": "openai", "kind": "api_key", "secret": "sk-openai"}

    monkeypatch.setattr(agent_auth, "_get_credential", cred)
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.CODEX and auth.env == {"OPENAI_API_KEY": "sk-openai"}


@pytest.mark.asyncio
async def test_byo_openrouter_key_runs_opencode(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def cred(_uid):
        return {"provider": "openrouter", "kind": "api_key", "secret": "sk-or"}

    monkeypatch.setattr(agent_auth, "_get_credential", cred)
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.OPENCODE and auth.env == {"OPENROUTER_API_KEY": "sk-or"}


@pytest.mark.asyncio
async def test_byo_claude_oauth_writes_credentials_file(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def cred(_uid):
        return {"provider": "anthropic", "kind": "oauth", "secret": '{"claudeAiOauth":{}}'}

    monkeypatch.setattr(agent_auth, "_get_credential", cred)
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.CLAUDE
    assert auth.env["CLAUDE_CONFIG_DIR"] == "/home/sprite/.claude"
    assert "/home/sprite/.claude/.credentials.json" in auth.files


@pytest.mark.asyncio
async def test_no_credential_pro_gets_managed_openrouter_glm(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-managed-or")

    async def no_cred(_uid):
        return None

    async def is_pro(_uid):
        return True

    monkeypatch.setattr(agent_auth, "_get_credential", no_cred)
    monkeypatch.setattr(billing_service, "is_pro", is_pro)
    auth = await agent_auth.resolve(uuid.uuid4())
    assert auth.harness is h.OPENCODE
    assert auth.harness.default_model == "z-ai/glm-5.2"
    assert auth.env == {"OPENROUTER_API_KEY": "sk-managed-or"}


@pytest.mark.asyncio
async def test_no_credential_free_is_gated(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def no_cred(_uid):
        return None

    async def not_pro(_uid):
        return False

    monkeypatch.setattr(agent_auth, "_get_credential", no_cred)
    monkeypatch.setattr(billing_service, "is_pro", not_pro)
    with pytest.raises(agent_auth.NeedsAuth):
        await agent_auth.resolve(uuid.uuid4())


@pytest.mark.asyncio
async def test_managed_but_no_openrouter_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)

    async def no_cred(_uid):
        return None

    async def is_pro(_uid):
        return True

    monkeypatch.setattr(agent_auth, "_get_credential", no_cred)
    monkeypatch.setattr(billing_service, "is_pro", is_pro)
    with pytest.raises(agent_auth.ProviderNotConfigured):
        await agent_auth.resolve(uuid.uuid4())


def test_openrouter_rejects_oauth():
    import asyncio

    with pytest.raises(ValueError):
        asyncio.get_event_loop().run_until_complete(
            agent_auth.store_credential(uuid.uuid4(), "openrouter", "oauth", "x")
        )
