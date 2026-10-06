"""Native recording reaches Traces without erasing an ongoing review."""

import gzip
import json
from uuid import UUID

from .conftest import unique_name


def codex(*answers):
    records = [{"type": "session_meta", "payload": {"id": "session1", "cwd": "/repo"}}]
    records += [
        {"type": "response_item", "payload": item}
        for item in [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix the failing test"}],
            },
            {
                "type": "function_call",
                "name": "exec",
                "arguments": '{"cmd":"pytest"}',
                "call_id": "call1",
            },
            {"type": "function_call_output", "call_id": "call1", "output": "1 failed"},
            *[
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": answer}],
                }
                for answer in answers
            ],
        ]
    ]
    return "\n".join(json.dumps(r) for r in records).encode()


async def register(client):
    response = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    user = response.json()
    return {"Authorization": f"Bearer {user['api_key']}"}, UUID(user["id"])


async def upload(client, auth, body, **data):
    response = await client.post(
        "/api/v1/me/transcripts",
        headers=auth,
        files={"file": ("session.jsonl.gz", gzip.compress(body), "application/gzip")},
        data={"session_id": "session1", "agent_name": "codex", **data},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_native_upload_creates_review_trace_and_preserves_review_on_append(client, pool):
    auth, owner = await register(client)
    first = await upload(client, auth, codex("Found the bug"))
    tid = first["trace"]["id"]
    detail = (await client.get(f"/api/v1/rm/traces/{tid}", headers=auth)).json()
    assert [s["role"] for s in detail["steps"]] == ["user", "assistant", "tool", "assistant"]
    assert detail["steps"][1]["tool_input"] == {"cmd": "pytest"}
    assert detail["steps"][2]["tool_name"] == "exec"
    assert detail["metadata"]["domain"] == "coding"
    step_id = detail["steps"][-1]["id"]
    comment = await client.post(
        f"/api/v1/rm/traces/{tid}/annotations",
        headers=auth,
        json={"step_id": step_id, "comment": "Show the test result"},
    )
    assert comment.status_code == 200
    second = await upload(client, auth, codex("Found the bug", "Fixed it; pytest passes"))
    assert second["skipped"] is True  # Legacy events already exist; trace still advances.
    assert second["trace"] == {"id": tid, "appended": 1}
    updated = (await client.get(f"/api/v1/rm/traces/{tid}", headers=auth)).json()
    assert updated["steps"][:4] == detail["steps"]
    assert len(updated["steps"]) == 5
    assert updated["annotations"][0]["step_id"] == step_id
    assert await pool.fetchval("SELECT count(*) FROM rm_traces WHERE owner_user_id=$1", owner) == 1


async def test_duplicate_and_stale_uploads_do_not_change_trace_or_scoring_queue(client, pool):
    auth, _ = await register(client)
    result = await upload(client, auth, codex("First", "Second"))
    tid = UUID(result["trace"]["id"])
    timestamp = await pool.fetchval("SELECT updated_at FROM rm_traces WHERE id=$1", tid)
    due_at = await pool.fetchval("SELECT due_at FROM rm_auto_scores WHERE trace_id=$1", tid)
    for body in (codex("First", "Second"), codex("First")):
        assert (await upload(client, auth, body))["trace"]["appended"] == 0
    assert await pool.fetchval("SELECT updated_at FROM rm_traces WHERE id=$1", tid) == timestamp
    assert await pool.fetchval("SELECT due_at FROM rm_auto_scores WHERE trace_id=$1", tid) == due_at


async def test_conflicting_snapshot_preserves_original_review(client, pool):
    auth, _ = await register(client)
    first = await upload(client, auth, codex("Original"))
    result = await upload(client, auth, codex("Rewritten"))
    assert "existing review preserved" in result["trace_sync_error"]
    tid = UUID(first["trace"]["id"])
    assert (
        await pool.fetchval("SELECT content FROM rm_trace_steps WHERE trace_id=$1 AND idx=3", tid)
        == "Original"
    )


async def test_flag_off_account_keeps_legacy_recording_only(client, pool):
    auth, owner = await register(client)
    await pool.execute("UPDATE users SET reward_models_enabled=false WHERE id=$1", owner)
    result = await upload(client, auth, codex("Done"))
    assert "trace" not in result
    assert await pool.fetchval("SELECT count(*) FROM rm_traces") == 0


async def test_deleted_session_is_not_recreated_as_trace(client, pool):
    auth, owner = await register(client)
    await pool.execute("UPDATE users SET reward_models_enabled=false WHERE id=$1", owner)
    await upload(client, auth, codex("Done"))
    await pool.execute("UPDATE sessions SET deleted_at=now() WHERE owner_user_id=$1", owner)
    await pool.execute("UPDATE users SET reward_models_enabled=true WHERE id=$1", owner)
    result = await upload(client, auth, codex("Done", "More"))
    assert result["reason"] == "session was deleted"
    assert await pool.fetchval("SELECT count(*) FROM rm_traces") == 0


async def test_other_account_cannot_read_imported_trace(client):
    auth, _ = await register(client)
    other, _ = await register(client)
    result = await upload(client, auth, codex("Done"))
    response = await client.get(f"/api/v1/rm/traces/{result['trace']['id']}", headers=other)
    assert response.status_code == 404


async def test_claude_code_upload_uses_native_adapter(client):
    auth, _ = await register(client)
    body = "\n".join(
        json.dumps(record)
        for record in [
            {
                "type": "user",
                "sessionId": "session1",
                "cwd": "/repo",
                "message": {"role": "user", "content": "Fix this"},
            },
            {
                "type": "assistant",
                "sessionId": "session1",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Done"}]},
            },
        ]
    ).encode()
    result = await upload(client, auth, body, agent_name="claude")
    detail = (await client.get(f"/api/v1/rm/traces/{result['trace']['id']}", headers=auth)).json()
    assert detail["source_format"] == "claude_code"
    assert len(detail["steps"]) == 2


async def test_mismatched_transcript_identity_is_not_mixed_into_another_session(client, pool):
    auth, _ = await register(client)
    result = await upload(client, auth, codex("Done"), session_id="different-session")
    assert "does not match" in result["trace_sync_error"]
    assert await pool.fetchval("SELECT count(*) FROM rm_traces") == 0


async def test_workspace_upload_does_not_copy_into_personal_traces(client, pool):
    from .test_developer_platform import _developer

    key, _, workspace = await _developer(client)
    auth = {"Authorization": f"Bearer {key}", "X-Stash-Scope": workspace["scope_user_id"]}
    result = await upload(client, auth, codex("Done"))
    assert "trace" not in result
    assert await pool.fetchval("SELECT count(*) FROM rm_traces") == 0
