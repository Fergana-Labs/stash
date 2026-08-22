"""Tests for the Stash MCP server.

Covers:
- StashTokenVerifier with valid / invalid API keys
- SSE endpoint auth behaviour (401 without token, 200 with token)

SSE tests must NOT hold the SSE connection open — the MCP SSE handler
never closes voluntarily, so we use ``asyncio.timeout()`` to abort.
"""

import asyncio
from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from mcp.server.auth.middleware.bearer_auth import AccessToken

from backend.services.mcp_service import StashTokenVerifier, mcp, stash_search

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    """Register a test user and return the API key."""
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mcp_user"), "password": "securepassword1"},
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


def _headers(key: str | None = None) -> dict:
    """Return headers dict, optionally with Authorization bearer.

    Includes a Host header with port so the MCP SDK's DNS rebinding
    wildcard check (``localhost:*`` → ``startswith("localhost:")``)
    passes.
    """
    h = {"Host": "localhost:0"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


# ---------------------------------------------------------------------------
# Token verifier tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verifier_valid_key(client: AsyncClient):
    """StashTokenVerifier resolves a real API key to an AccessToken."""
    api_key = await _register(client)
    verifier = StashTokenVerifier()
    result = await verifier.verify_token(api_key)

    assert result is not None
    assert result.subject is not None
    assert len(result.subject) > 0  # UUID string
    assert result.client_id == result.subject  # same user
    assert result.token == api_key


@pytest.mark.asyncio
async def test_verifier_invalid_key():
    """StashTokenVerifier returns None for a bogus API key."""
    result = await StashTokenVerifier().verify_token("st_invalid_key_12345")
    assert result is None


# ---------------------------------------------------------------------------
# SSE endpoint tests
#
# WARNING: The MCP SSE handler never closes the connection by itself, so
# a plain ``client.get()`` hangs forever.  We run the request in a task
# with a short timeout, check status/headers, and let the timeout abort it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_endpoint_auth_required(client: AsyncClient):
    """The /api/v1/mcp/sse endpoint rejects unauthenticated requests with 401."""
    # No auth header — the BearerAuthBackend rejects before the SSE handler.
    r = await client.get("/api/v1/mcp/sse", headers=_headers())
    assert r.status_code == 401, f"expected 401, got {r.status_code}"

    # Valid key — SSE connection opens.  Abort with a timeout.
    api_key = await _register(client)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(3):
            r = await client.get("/api/v1/mcp/sse", headers=_headers(api_key))
            assert r.status_code == 200, f"expected 200, got {r.status_code}"
            ct = r.headers.get("content-type", "")
            assert ct.startswith("text/event-stream"), f"expected SSE content type, got {ct}"
            # If we get here, the response started — the timeout will abort
            # the open SSE connection.


@pytest.mark.asyncio
async def test_sse_endpoint_authenticated(client: AsyncClient):
    """Authenticated request to SSE endpoint returns 200 with SSE content type."""
    api_key = await _register(client)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(3):
            r = await client.get("/api/v1/mcp/sse", headers=_headers(api_key))
            assert r.status_code == 200, f"expected 200, got {r.status_code}"
            ct = r.headers.get("content-type", "")
            assert ct.startswith("text/event-stream"), f"expected SSE content type, got {ct}"


# ---------------------------------------------------------------------------
# stash_search tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stash_search_registered():
    """stash_search is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_search" in tool_names, f"stash_search not found in {tool_names}"

    tool = next(t for t in tools if t.name == "stash_search")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    # query is a required string
    assert "query" in props
    assert props["query"]["type"] == "string"
    assert "query" in schema.get("required", [])

    # limit is an optional integer with default 10
    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert "limit" not in schema.get("required", [])
    assert props["limit"].get("default") == 10


@pytest.mark.asyncio
async def test_stash_search_calls_service():
    """stash_search calls source_service.search_all with correct args."""
    fake_results = [
        {
            "source": "native-files",
            "ref": "abc-123",
            "name": "test page",
            "snippet": "some content",
        }
    ]
    fake_token = AsyncMock()
    fake_token.subject = "00000000-0000-0000-0000-000000000001"

    mock_search = AsyncMock(return_value=fake_results)

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.mcp_service.source_service.search_all", mock_search):
            result = await stash_search(query="test query", limit=5)

    # Verify search_all was called with the right args
    mock_search.assert_awaited_once_with(
        fake_token.subject, fake_token.subject, "test query", limit=5
    )

    # Verify result is correct JSON
    import json

    parsed = json.loads(result)
    assert parsed == fake_results


@pytest.mark.asyncio
async def test_stash_search_none_results():
    """stash_search returns [] when search_all returns None."""
    fake_token = AsyncMock()
    fake_token.subject = "00000000-0000-0000-0000-000000000002"

    mock_search = AsyncMock(return_value=None)

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.mcp_service.source_service.search_all", mock_search):
            result = await stash_search(query="nothing")

    assert result == "[]"


# ---------------------------------------------------------------------------
# stash_session_search tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_search_registered():
    """stash_session_search is registered as an MCP tool with correct schema."""
    from backend.services.mcp_service import mcp

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_session_search" in tool_names

    tool = next(t for t in tools if t.name == "stash_session_search")
    # MCP SDK uses inputSchema which is a JSON schema dict
    schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
    props = schema.get("properties", {})
    assert "query" in props
    assert props["query"]["type"] == "string"
    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert props["limit"].get("default") == 10


@pytest.mark.asyncio
async def test_session_search_auth_required():
    """Returns auth error when no token is available."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_session_search

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_session_search("test query")

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


@pytest.mark.asyncio
async def test_session_search_returns_json_envelope():
    """Returns structured JSON with query, count, and results keys."""
    import json
    from datetime import datetime
    from unittest.mock import patch
    from uuid import UUID

    from backend.services.mcp_service import stash_session_search

    fake_token = AccessToken(
        token="test-token",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        subject="550e8400-e29b-41d4-a716-446655440000",
        scopes=["stash:full"],
    )
    fake_events = [
        {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "session_id": "sess_abc",
            "agent_name": "claude-code",
            "event_type": "user_message",
            "content": "How do I implement this?",
            "created_at": datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC),
            "rank": 0.85,
        },
        {
            "id": UUID("22222222-2222-2222-2222-222222222222"),
            "session_id": "sess_def",
            "agent_name": "claude-code",
            "event_type": "assistant_message",
            "content": "Here's how you can implement that.",
            "created_at": datetime(2026, 7, 14, 12, 5, 0, tzinfo=UTC),
            "rank": 0.72,
        },
    ]

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.memory_service.search_scope_events",
            return_value=fake_events,
        ),
    ):
        result = await stash_session_search("test query")

    parsed = json.loads(result)
    assert parsed["query"] == "test query"
    assert parsed["count"] == 2
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["session_id"] == "sess_abc"
    assert parsed["results"][1]["agent_name"] == "claude-code"


@pytest.mark.asyncio
async def test_session_search_empty_results():
    """Returns count: 0 and results: [] when no matches."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_session_search

    fake_token = AccessToken(
        token="test-token",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        subject="550e8400-e29b-41d4-a716-446655440000",
        scopes=["stash:full"],
    )

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.memory_service.search_scope_events",
            return_value=[],
        ),
    ):
        result = await stash_session_search("no matches")

    parsed = json.loads(result)
    assert parsed["count"] == 0
    assert parsed["results"] == []


@pytest.mark.asyncio
async def test_session_search_calls_service_with_correct_args():
    """Calls search_scope_events with the authenticated user and correct params."""
    from unittest.mock import patch
    from uuid import UUID

    from backend.services.mcp_service import stash_session_search

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.memory_service.search_scope_events",
            return_value=[],
        ) as mock_search,
    ):
        await stash_session_search("test", limit=5)

    mock_search.assert_awaited_once_with(
        owner_user_id=UUID(user_uuid),
        user_id=UUID(user_uuid),
        query="test",
        limit=5,
    )


# ---------------------------------------------------------------------------
# stash_vfs_ls tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stash_vfs_ls_registered():
    """stash_vfs_ls is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_vfs_ls" in tool_names

    tool = next(t for t in tools if t.name == "stash_vfs_ls")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    assert "path" in props
    assert props["path"]["type"] == "string"
    assert props["path"].get("default") == "/"
    assert "path" not in schema.get("required", [])


@pytest.mark.asyncio
async def test_stash_vfs_ls_lists_root():
    """stash_vfs_ls(path="/") returns top-level VFS sections."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_ls

    fake_token = AsyncMock()
    fake_token.token = "st_test_key"

    fake_result = {
        "stdout": "files\nsessions\nsources\nmemory\ntables\nskills\n",
        "stderr": "",
        "exit_code": 0,
        "cwd": "/",
    }

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.vfs_service.run_vfs_script", return_value=fake_result):
            result = await stash_vfs_ls()

    import json

    parsed = json.loads(result)
    assert parsed["path"] == "/"
    assert parsed["is_dir"] is True
    assert "files" in parsed["entries"]
    assert "sessions" in parsed["entries"]
    assert parsed["entry_count"] >= 1
    assert parsed["type"] == "directory"


@pytest.mark.asyncio
async def test_stash_vfs_ls_nonexistent():
    """Non-existent path returns structured error."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_ls

    fake_token = AsyncMock()
    fake_token.token = "st_test_key"

    fake_result = {
        "stdout": "",
        "stderr": "ls: /nonexistent: No such file or directory\n",
        "exit_code": 1,
        "cwd": "/",
    }

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.vfs_service.run_vfs_script", return_value=fake_result):
            result = await stash_vfs_ls(path="/nonexistent")

    import json

    parsed = json.loads(result)
    assert "error" in parsed
    assert parsed["path"] == "/nonexistent"


@pytest.mark.asyncio
async def test_stash_vfs_ls_auth_required():
    """Returns auth error when no token is available."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_ls

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_vfs_ls()

    import json

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


# ---------------------------------------------------------------------------
# stash_vfs_cat tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vfs_cat_registered():
    """stash_vfs_cat is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_vfs_cat" in tool_names

    tool = next(t for t in tools if t.name == "stash_vfs_cat")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    assert "path" in props
    assert props["path"]["type"] == "string"
    assert "path" in schema.get("required", [])


@pytest.mark.asyncio
async def test_vfs_cat_read_file():
    """stash_vfs_cat returns file content for a valid path."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_cat

    fake_token = AsyncMock()
    fake_token.token = "st_test_key"

    fake_result = {
        "stdout": "# Hello World\n\nThis is a test file.\n",
        "stderr": "",
        "exit_code": 0,
        "cwd": "/",
    }

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.vfs_service.run_vfs_script", return_value=fake_result):
            result = await stash_vfs_cat(path="/files/test.md")

    import json

    parsed = json.loads(result)
    assert parsed["path"] == "/files/test.md"
    assert parsed["content"] == "# Hello World\n\nThis is a test file.\n"
    assert parsed["size"] == 36


@pytest.mark.asyncio
async def test_vfs_cat_nonexistent_path():
    """Non-existent path returns structured error."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_cat

    fake_token = AsyncMock()
    fake_token.token = "st_test_key"

    fake_result = {
        "stdout": "",
        "stderr": "cat: /nonexistent: No such file or directory\n",
        "exit_code": 1,
        "cwd": "/",
    }

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.vfs_service.run_vfs_script", return_value=fake_result):
            result = await stash_vfs_cat(path="/nonexistent")

    import json

    parsed = json.loads(result)
    assert "error" in parsed
    assert parsed["path"] == "/nonexistent"


@pytest.mark.asyncio
async def test_vfs_cat_empty_file():
    """Empty stdout returns descriptive error."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_cat

    fake_token = AsyncMock()
    fake_token.token = "st_test_key"

    fake_result = {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "cwd": "/",
    }

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        with patch("backend.services.vfs_service.run_vfs_script", return_value=fake_result):
            result = await stash_vfs_cat(path="/files/binary.bin")

    import json

    parsed = json.loads(result)
    assert "error" in parsed
    assert "empty or binary" in parsed["error"]
    assert parsed["path"] == "/files/binary.bin"


@pytest.mark.asyncio
async def test_vfs_cat_auth_required():
    """Returns auth error when no token is available."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_vfs_cat

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_vfs_cat(path="/files/test.md")

    import json

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# stash_session_upload tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_upload_registered():
    """stash_session_upload is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_session_upload" in tool_names

    tool = next(t for t in tools if t.name == "stash_session_upload")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    # session_id is a required string
    assert "session_id" in props
    assert props["session_id"]["type"] == "string"
    assert "session_id" in schema.get("required", [])

    # agent_name is an optional string with empty default
    assert "agent_name" in props
    assert props["agent_name"]["type"] == "string"
    assert "agent_name" not in schema.get("required", [])

    # cwd is an optional string|null (MCP SDK uses anyOf for str | None)
    assert "cwd" in props
    assert "string" in [s.get("type") for s in props["cwd"].get("anyOf", [])]
    assert "cwd" not in schema.get("required", [])

    # events is an optional string with "[]" default
    assert "events" in props
    assert props["events"]["type"] == "string"
    assert "events" not in schema.get("required", [])

    # replace is an optional boolean with default false
    assert "replace" in props
    assert props["replace"]["type"] == "boolean"
    assert "replace" not in schema.get("required", [])


@pytest.mark.asyncio
async def test_session_upload_auth_required():
    """Returns auth error when no token is available."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_session_upload

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_session_upload(session_id="sess_test")

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


@pytest.mark.asyncio
async def test_session_upload_creates_session_and_events():
    """Happy path: creates session and pushes events, returns correct counts."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_session_upload

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    fake_session = {"id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), "session_id": "sess_test"}
    fake_events = [{"id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")}]

    # Mock pool.fetchval to return 0 (no existing events)
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=0)

    with (
        patch("backend.services.mcp_service.get_access_token", return_value=fake_token),
        patch(
            "backend.services.session_service.upsert_session", return_value=fake_session
        ) as mock_upsert,
        patch(
            "backend.services.memory_service.push_events_batch", return_value=fake_events
        ) as mock_push,
        patch("backend.database.get_pool", return_value=mock_pool),
    ):
        result = await stash_session_upload(
            session_id="sess_test",
            agent_name="test-agent",
            events='[{"event_type": "user_message", "content": "hello", "agent_name": "test-agent"}]',
        )

    parsed = json.loads(result)
    assert parsed["session_id"] == "sess_test"
    assert parsed["event_count"] == 1
    assert parsed["imported"] == 1

    mock_upsert.assert_awaited_once()
    mock_push.assert_awaited_once()
    # Verify push_events_batch got the right owner_user_id
    args, _ = mock_push.await_args
    assert args[0] == UUID(user_uuid)  # owner_user_id


@pytest.mark.asyncio
async def test_session_upload_empty_events():
    """Empty events array returns imported: 0."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_session_upload

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    fake_session = {"id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), "session_id": "sess_empty"}

    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=0)

    with (
        patch("backend.services.mcp_service.get_access_token", return_value=fake_token),
        patch("backend.services.session_service.upsert_session", return_value=fake_session),
        patch("backend.database.get_pool", return_value=mock_pool),
    ):
        result = await stash_session_upload(
            session_id="sess_empty",
            agent_name="test-agent",
            events="[]",
        )

    parsed = json.loads(result)
    assert parsed["session_id"] == "sess_empty"
    assert parsed["event_count"] == 0
    assert parsed["imported"] == 0


@pytest.mark.asyncio
async def test_session_upload_missing_event_type():
    """Events missing required event_type return a clear error."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_session_upload

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    with patch("backend.services.mcp_service.get_access_token", return_value=fake_token):
        result = await stash_session_upload(
            session_id="sess_bad",
            events='[{"content": "hello without event_type"}]',
        )

    parsed = json.loads(result)
    assert "error" in parsed
    assert "event_type" in parsed["error"]


@pytest.mark.asyncio
async def test_session_upload_idempotent():
    """Returns skipped=True when session already has events (no replace)."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_session_upload

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    fake_session = {
        "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "session_id": "sess_existing",
    }

    # Mock pool.fetchval to return 5 (existing events found)
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=5)

    with (
        patch("backend.services.mcp_service.get_access_token", return_value=fake_token),
        patch(
            "backend.services.session_service.upsert_session", return_value=fake_session
        ) as mock_upsert,
        patch("backend.services.memory_service.push_events_batch") as mock_push,
        patch("backend.database.get_pool", return_value=mock_pool),
    ):
        result = await stash_session_upload(
            session_id="sess_existing",
            agent_name="test-agent",
            events='[{"event_type": "user_message", "content": "hello"}]',
            replace=False,
        )

    parsed = json.loads(result)
    assert parsed["session_id"] == "sess_existing"
    assert parsed["imported"] == 0
    assert parsed["skipped"] is True
    assert "reason" in parsed

    # push_events_batch should NOT have been called
    mock_push.assert_not_awaited()
    # But upsert_session should still be called for metadata refresh
    mock_upsert.assert_awaited_once()


# ---------------------------------------------------------------------------
# stash_memory_search tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_search_registered():
    """stash_memory_search is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_memory_search" in tool_names

    tool = next(t for t in tools if t.name == "stash_memory_search")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    assert "query" in props
    assert props["query"]["type"] == "string"
    assert "query" in schema.get("required", [])

    assert "scope" in props
    assert "anyOf" in props["scope"]
    assert any(alt["type"] == "string" for alt in props["scope"]["anyOf"])
    assert any(alt["type"] == "null" for alt in props["scope"]["anyOf"])
    assert "scope" not in schema.get("required", [])

    assert "layer" in props
    assert "anyOf" in props["layer"]
    assert any(alt["type"] == "string" for alt in props["layer"]["anyOf"])
    assert any(alt["type"] == "null" for alt in props["layer"]["anyOf"])
    assert "layer" not in schema.get("required", [])

    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert props["limit"].get("default") == 5
    assert "limit" not in schema.get("required", [])


@pytest.mark.asyncio
async def test_memory_search_auth_required():
    """Returns auth error when no token is available."""
    from unittest.mock import patch

    from backend.services.mcp_service import stash_memory_search

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_memory_search("test query")

    import json

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


@pytest.mark.asyncio
async def test_memory_search_calls_service():
    """Returns structured JSON with query, count, and results keys."""
    import json
    from datetime import datetime
    from unittest.mock import patch
    from uuid import UUID

    from backend.services.mcp_service import stash_memory_search

    fake_token = AccessToken(
        token="test-token",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        subject="550e8400-e29b-41d4-a716-446655440000",
        scopes=["stash:full"],
    )
    fake_pages = [
        {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "name": "Architecture Overview",
            "folder_id": UUID("22222222-2222-2222-2222-222222222222"),
            "search_text": "The system uses a microservices architecture",
            "content_type": "markdown",
            "updated_at": datetime(2026, 7, 14, 12, 0, 0),
            "rank": 0.95,
        },
        {
            "id": UUID("33333333-3333-3333-3333-333333333333"),
            "name": "API Design",
            "folder_id": UUID("44444444-4444-4444-4444-444444444444"),
            "search_text": "RESTful API design principles",
            "content_type": "markdown",
            "updated_at": datetime(2026, 7, 13, 10, 0, 0),
            "rank": 0.72,
        },
    ]

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.files_tree_service.search_memory_pages_fts",
            return_value=fake_pages,
        ) as mock_search,
    ):
        result = await stash_memory_search("architecture", limit=3)

    parsed = json.loads(result)
    assert parsed["query"] == "architecture"
    assert parsed["count"] == 2
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["name"] == "Architecture Overview"
    assert parsed["results"][0]["id"] == str(fake_pages[0]["id"])
    assert parsed["results"][1]["name"] == "API Design"
    assert parsed["results"][1]["id"] == str(fake_pages[1]["id"])

    mock_search.assert_awaited_once_with(
        owner_user_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        query="architecture",
        limit=3,
        user_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    )


@pytest.mark.asyncio
async def test_memory_search_empty_results():
    """Returns count: 0 and results: [] when no matches."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_memory_search

    fake_token = AccessToken(
        token="test-token",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        subject="550e8400-e29b-41d4-a716-446655440000",
        scopes=["stash:full"],
    )

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.files_tree_service.search_memory_pages_fts",
            return_value=[],
        ),
    ):
        result = await stash_memory_search("no matches")

    parsed = json.loads(result)
    assert parsed["query"] == "no matches"
    assert parsed["count"] == 0
    assert parsed["results"] == []


@pytest.mark.asyncio
async def test_memory_search_default_params():
    """Uses default limit=5 when not specified."""
    from unittest.mock import patch
    from uuid import UUID

    from backend.services.mcp_service import stash_memory_search

    fake_token = AccessToken(
        token="test-token",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        subject="550e8400-e29b-41d4-a716-446655440000",
        scopes=["stash:full"],
    )

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.files_tree_service.search_memory_pages_fts",
            return_value=[],
        ) as mock_search,
    ):
        await stash_memory_search("test")

    mock_search.assert_awaited_once_with(
        owner_user_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        query="test",
        limit=5,
        user_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    )


# ---------------------------------------------------------------------------
# stash_memory_append tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_append_registered():
    """stash_memory_append is registered as an MCP tool with correct schema."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stash_memory_append" in tool_names

    tool = next(t for t in tools if t.name == "stash_memory_append")
    schema = tool.inputSchema
    props = schema.get("properties", {})

    assert "scope" in props
    assert props["scope"]["type"] == "string"
    assert "scope" in schema.get("required", [])

    assert "layer" in props
    assert props["layer"]["type"] == "string"
    assert "layer" in schema.get("required", [])

    assert "content" in props
    assert props["content"]["type"] == "string"
    assert "content" in schema.get("required", [])


@pytest.mark.asyncio
async def test_memory_append_creates_new_page():
    """When no existing page, creates a new page with correct name."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_memory_append

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    memory_folder_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_memory = {"id": memory_folder_id}

    new_page_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    fake_page = {
        "id": new_page_id,
        "name": "project-long-term",
        "app_url": "https://joinstash.ai/memory/project-long-term",
    }

    # Mock pool.fetchrow to return None (no existing page)
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.files_tree_service.get_or_create_memory_folder",
            return_value=fake_memory,
        ),
        patch(
            "backend.services.files_tree_service.create_page",
            return_value=fake_page,
        ) as mock_create_page,
        patch("backend.database.get_pool", return_value=mock_pool),
    ):
        result = await stash_memory_append(
            scope="project",
            layer="long-term",
            content="# Test memory entry\n\nSome important context.",
        )

    parsed = json.loads(result)
    assert parsed["page_id"] == str(new_page_id)
    assert parsed["name"] == "project-long-term"
    assert parsed["action"] == "created"
    assert parsed["app_url"] == fake_page["app_url"]

    mock_create_page.assert_awaited_once_with(
        owner_user_id=UUID(user_uuid),
        name="project-long-term",
        created_by=UUID(user_uuid),
        folder_id=memory_folder_id,
        content="# Test memory entry\n\nSome important context.",
    )


@pytest.mark.asyncio
async def test_memory_append_appends_to_existing():
    """When page exists, appends content with timestamp separator."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_memory_append

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    memory_folder_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_memory = {"id": memory_folder_id}

    page_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    existing_content = "# Existing memory\n\nPrevious entry."

    # Mock pool.fetchrow to return an existing page
    existing_row = {
        "id": page_id,
        "owner_user_id": UUID(user_uuid),
        "folder_id": memory_folder_id,
        "name": "agent-daily",
        "content_markdown": existing_content,
    }
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=existing_row)

    fake_updated = {
        "id": page_id,
        "name": "agent-daily",
        "app_url": "https://joinstash.ai/memory/agent-daily",
    }

    with (
        patch(
            "backend.services.mcp_service.get_access_token",
            return_value=fake_token,
        ),
        patch(
            "backend.services.files_tree_service.get_or_create_memory_folder",
            return_value=fake_memory,
        ),
        patch(
            "backend.services.files_tree_service.update_page",
            return_value=fake_updated,
        ) as mock_update_page,
        patch("backend.database.get_pool", return_value=mock_pool),
    ):
        result = await stash_memory_append(
            scope="agent",
            layer="daily",
            content="New observation for today.",
        )

    parsed = json.loads(result)
    assert parsed["page_id"] == str(page_id)
    assert parsed["name"] == "agent-daily"
    assert parsed["action"] == "appended"
    assert parsed["app_url"] == fake_updated["app_url"]

    # Verify update_page was called with merged content
    # The merged content should start with existing + newline + heading with timestamp
    _args, kwargs = mock_update_page.await_args
    assert kwargs["page_id"] == page_id
    assert kwargs["owner_user_id"] == UUID(user_uuid)
    assert kwargs["updated_by"] == UUID(user_uuid)
    assert kwargs["content"].startswith(existing_content + "\n\n## ")
    assert "New observation for today." in kwargs["content"]


@pytest.mark.asyncio
async def test_memory_append_auth_required():
    """Returns auth error when no token is available."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_memory_append

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_memory_append(scope="project", layer="long-term", content="test")

    parsed = json.loads(result)
    assert parsed == {"error": "Authentication required"}


@pytest.mark.asyncio
async def test_memory_append_invalid_scope():
    """Returns error for invalid scope value."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_memory_append

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_memory_append(scope="invalid-scope", layer="long-term", content="test")

    parsed = json.loads(result)
    assert "error" in parsed
    assert "Invalid scope" in parsed["error"]


@pytest.mark.asyncio
async def test_memory_append_invalid_layer():
    """Returns error for invalid layer value."""
    import json
    from unittest.mock import patch

    from backend.services.mcp_service import stash_memory_append

    with patch("backend.services.mcp_service.get_access_token", return_value=None):
        result = await stash_memory_append(scope="project", layer="invalid-layer", content="test")

    parsed = json.loads(result)
    assert "error" in parsed
    assert "Invalid layer" in parsed["error"]


@pytest.mark.asyncio
async def test_memory_append_all_scope_layer_combinations():
    """All 4 scope/layer combinations produce distinct page names."""
    import json
    from unittest.mock import AsyncMock, patch
    from uuid import UUID

    from backend.services.mcp_service import stash_memory_append

    user_uuid = "550e8400-e29b-41d4-a716-446655440000"
    fake_token = AccessToken(
        token="test-token",
        client_id=user_uuid,
        subject=user_uuid,
        scopes=["stash:full"],
    )

    memory_folder_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_memory = {"id": memory_folder_id}

    # Mock pool.fetchrow to return None (no existing page each time)
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    combinations = [
        ("agent", "long-term", "agent-long-term"),
        ("agent", "daily", "agent-daily"),
        ("project", "long-term", "project-long-term"),
        ("project", "daily", "project-daily"),
    ]

    for scope, layer, expected_name in combinations:
        page_id = UUID(f"{hash(scope + layer) & 0xFFFFFFFF:08x}-0000-0000-0000-000000000000"[:36])
        fake_page = {"id": page_id, "name": expected_name, "app_url": ""}

        with (
            patch(
                "backend.services.mcp_service.get_access_token",
                return_value=fake_token,
            ),
            patch(
                "backend.services.files_tree_service.get_or_create_memory_folder",
                return_value=fake_memory,
            ),
            patch(
                "backend.services.files_tree_service.create_page",
                return_value=fake_page,
            ) as mock_create_page,
            patch("backend.database.get_pool", return_value=mock_pool),
        ):
            result = await stash_memory_append(scope=scope, layer=layer, content="test")

        parsed = json.loads(result)
        assert parsed["name"] == expected_name
        assert parsed["action"] == "created"

        # Verify create_page was called with the expected name
        _, kwargs = mock_create_page.await_args
        assert kwargs["name"] == expected_name
