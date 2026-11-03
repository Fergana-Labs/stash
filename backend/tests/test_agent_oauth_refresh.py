"""A stored OAuth credential must survive the harness refreshing it on the box.

Claude Code and Codex refresh their own token inside the sandbox, and the
provider rotates the refresh token when they do. The box is rewritten from the
stored credential before every turn, so a refresh that is never stored leaves
the next turn holding a spent refresh token: every Claude-OAuth curator in
production failed nightly with "OAuth session expired and could not be
refreshed" about a day after its owner connected (Oct 2026).
"""

import json
import uuid

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.database import get_pool
from backend.services import agent_auth, sprite_agent_service, sprite_service

from .conftest import stream_json_reply, unique_name

CLAUDE_FILE = "/home/sprite/.claude/.credentials.json"
CODEX_FILE = "/home/sprite/.codex/auth.json"


def _claude(access: str, refresh: str, expires_at: int) -> str:
    return json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": access,
                "refreshToken": refresh,
                "expiresAt": expires_at,
                "scopes": ["user:inference"],
                "subscriptionType": "max",
            }
        }
    )


async def _register(client: AsyncClient) -> uuid.UUID:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("oauth"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def _stored(user_id: uuid.UUID, provider: str) -> dict:
    return json.loads((await agent_auth._get_credential(user_id, provider))["secret"])


class _RotatingClaude:
    """Stands in for the Claude CLI and Anthropic's token endpoint: the access
    token in the box's credential file is expired at the start of every turn,
    so the CLI refreshes — and each refresh token works exactly once."""

    def __init__(self, files: dict[str, str], first_refresh_token: str) -> None:
        self.files = files
        self.valid_refresh_token = first_refresh_token
        self.refreshes = 0

    async def exec_stream(self, sprite, argv, *, env, cwd=None):
        tokens = json.loads(self.files[CLAUDE_FILE])["claudeAiOauth"]
        if tokens["refreshToken"] != self.valid_refresh_token:
            error = "Failed to authenticate: OAuth session expired and could not be refreshed"
            line = json.dumps(
                {"type": "result", "subtype": "error", "is_error": True, "result": error}
            )
            yield {"stream": "stdout", "data": (line + "\n").encode()}
            yield {"exit_code": 1}
            return
        self.refreshes += 1
        self.valid_refresh_token = f"rt-{self.refreshes}"
        self.files[CLAUDE_FILE] = _claude(
            f"at-{self.refreshes}", self.valid_refresh_token, tokens["expiresAt"] + 3_600_000
        )
        for line in stream_json_reply("done"):
            yield {"stream": "stdout", "data": (line + "\n").encode()}
        yield {"exit_code": 0}


@pytest.mark.asyncio
async def test_claude_oauth_keeps_working_across_token_rotations(client, sprite_exec, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    user_id = await _register(client)
    await agent_auth.store_credential(user_id, "anthropic", "oauth", _claude("at-0", "rt-0", 1000))
    cli = _RotatingClaude(sprite_exec.files, "rt-0")
    monkeypatch.setattr(sprite_service, "exec_stream", cli.exec_stream)

    for night in range(3):
        reply = await sprite_agent_service.run_chat(
            user_id, "Owner", user_id, f"agent-test-{uuid.uuid4()}", f"curate night {night}"
        )
        assert reply == "done"

    assert cli.refreshes == 3
    assert (await _stored(user_id, "anthropic"))["claudeAiOauth"]["refreshToken"] == "rt-3"


@pytest.mark.asyncio
async def test_failed_turn_still_stores_a_refreshed_token(client, sprite_exec, monkeypatch):
    """The refresh and the turn are separate outcomes: a turn that refreshed
    and then failed has still spent the stored refresh token."""
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    user_id = await _register(client)
    await agent_auth.store_credential(user_id, "anthropic", "oauth", _claude("at-0", "rt-0", 1000))

    async def refresh_then_crash(sprite, argv, *, env, cwd=None):
        sprite_exec.files[CLAUDE_FILE] = _claude("at-1", "rt-1", 2000)
        yield {"stream": "stdout", "data": b"boom\n"}
        yield {"exit_code": 1}

    monkeypatch.setattr(sprite_service, "exec_stream", refresh_then_crash)
    with pytest.raises(RuntimeError, match="agent turn failed"):
        await sprite_agent_service.run_chat(
            user_id, "Owner", user_id, f"agent-test-{uuid.uuid4()}", "hello"
        )

    assert (await _stored(user_id, "anthropic"))["claudeAiOauth"]["refreshToken"] == "rt-1"


@pytest.mark.asyncio
async def test_read_back_failure_does_not_fail_the_turn(client, sprite_exec, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    user_id = await _register(client)
    await agent_auth.store_credential(user_id, "anthropic", "oauth", _claude("at-0", "rt-0", 1000))

    async def broken_read(sprite, abs_path):
        raise sprite_service.SpriteError("box went away")

    monkeypatch.setattr(sprite_service, "read_file", broken_read)
    reply = await sprite_agent_service.run_chat(
        user_id, "Owner", user_id, f"agent-test-{uuid.uuid4()}", "hello"
    )
    assert reply.startswith("Reply to:")
    assert (await _stored(user_id, "anthropic"))["claudeAiOauth"]["refreshToken"] == "rt-0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contents",
    [
        _claude("at-0", "rt-0", 1000),  # untouched by the CLI
        _claude("at-1", "rt-1", 500),  # older than stored: the user reconnected mid-turn
        _claude("at-1", "", 2000),  # no refresh token
        json.dumps({"claudeAiOauth": {}}),  # the CLI logged itself out
        "not json",
        "[]",
    ],
)
async def test_save_refreshed_ignores_files_that_are_not_a_newer_token(client, contents):
    user_id = await _register(client)
    original = _claude("at-0", "rt-0", 1000)
    await agent_auth.store_credential(user_id, "anthropic", "oauth", original)
    oauth_file = agent_auth.OAuthFile(user_id, "anthropic", CLAUDE_FILE)

    assert await agent_auth.save_refreshed(oauth_file, contents) is False
    assert await _stored(user_id, "anthropic") == json.loads(original)


@pytest.mark.asyncio
async def test_save_refreshed_never_recreates_or_overwrites_a_non_oauth_credential(client):
    user_id = await _register(client)
    oauth_file = agent_auth.OAuthFile(user_id, "anthropic", CLAUDE_FILE)
    fresh = _claude("at-1", "rt-1", 2000)

    # Disconnected mid-turn: nothing to update, and nothing is created.
    assert await agent_auth.save_refreshed(oauth_file, fresh) is False
    assert await agent_auth.list_connected(user_id) == []

    # Switched to an API key mid-turn: the key stays.
    await agent_auth.store_credential(user_id, "anthropic", "api_key", "sk-ant-mine")
    assert await agent_auth.save_refreshed(oauth_file, fresh) is False
    assert (await agent_auth._get_credential(user_id, "anthropic"))["secret"] == "sk-ant-mine"


@pytest.mark.asyncio
async def test_save_refreshed_keeps_the_connected_at_timestamp(client):
    user_id = await _register(client)
    await agent_auth.store_credential(user_id, "anthropic", "oauth", _claude("at-0", "rt-0", 1000))
    query = "SELECT created_at FROM user_agent_credentials WHERE user_id = $1"
    connected_at = await get_pool().fetchval(query, user_id)

    oauth_file = agent_auth.OAuthFile(user_id, "anthropic", CLAUDE_FILE)
    assert await agent_auth.save_refreshed(oauth_file, _claude("at-1", "rt-1", 2000)) is True
    assert await get_pool().fetchval(query, user_id) == connected_at


@pytest.mark.asyncio
async def test_codex_refresh_is_stored_and_written_back_verbatim(client):
    user_id = await _register(client)
    # Connect stores the bare token set; the box gets it wrapped as auth.json.
    bare = {"access_token": "at-0", "id_token": "id-0", "refresh_token": "rt-0", "account_id": "a"}
    await agent_auth.store_credential(user_id, "openai", "oauth", json.dumps(bare))
    oauth_file = agent_auth.OAuthFile(user_id, "openai", CODEX_FILE)

    unchanged = json.dumps({"OPENAI_API_KEY": None, "tokens": bare, "last_refresh": "t0"})
    assert await agent_auth.save_refreshed(oauth_file, unchanged) is False

    rotated = json.dumps(
        {
            "OPENAI_API_KEY": None,
            "tokens": {**bare, "access_token": "at-1", "refresh_token": "rt-1"},
            "last_refresh": "t1",
        }
    )
    assert await agent_auth.save_refreshed(oauth_file, rotated) is True
    cred = await agent_auth._get_credential(user_id, "openai")
    assert agent_auth._byo_auth(cred).files[CODEX_FILE] == rotated
