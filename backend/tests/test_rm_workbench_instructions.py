"""A released version reaches only its intended runs and needs context proof."""

from uuid import UUID

import pytest

from backend.services import session_service
from backend.services.rm import session_ingest
from backend.services.rm import workbench_instructions as instructions
from stashai.plugin.workbench import instruction_context

from .conftest import unique_name


async def owner(client):
    response = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


async def grader(pool, user, scope=None):
    return await pool.fetchval(
        "INSERT INTO rm_wb_graders(owner_user_id,name,scope) VALUES($1,'Test reporting',$2) RETURNING id",
        user,
        scope or {"source_format": "codex", "repository": "/repo"},
    )


async def change(
    pool, user, grader_id, text="Check test results.", *, status="checked", parent=None
):
    return await pool.fetchval(
        "INSERT INTO rm_wb_changes(owner_user_id,grader_id,kind,status,title,content,parent_version_id,check_report) "
        "VALUES($1,$2,'instruction',$3,'Check test reports',$4,$5,$6) RETURNING id",
        user,
        grader_id,
        status,
        {"text": text},
        parent,
        {"passed": True, "quality_measured": False},
    )


async def session(user, session_id, cwd="/repo"):
    return await session_service.upsert_session(user, session_id, agent_name="codex", cwd=cwd)


async def test_draft_never_delivered_and_release_is_owner_scoped(client, pool):
    user, other = await owner(client), await owner(client)
    gid = await grader(pool, user)
    cid = await change(pool, user, gid, status="draft")
    await session(user, "before")
    assert (await instructions.deliver(user, "before", "codex", "/repo"))["deliveries"] == []
    with pytest.raises(instructions.InstructionInvalid, match="checked"):
        await instructions.release_instruction(user, cid)
    await pool.execute("UPDATE rm_wb_changes SET status='checked' WHERE id=$1", cid)
    with pytest.raises(instructions.InstructionInvalid, match="not found"):
        await instructions.release_instruction(other, cid)
    await instructions.release_instruction(user, cid)
    # An already-running session cannot silently acquire the new instruction.
    assert (await instructions.deliver(user, "before", "codex", "/repo"))["deliveries"] == []
    await session(user, "after")
    delivered = await instructions.deliver(user, "after", "codex", "/repo/")
    assert len(delivered["deliveries"]) == 1
    assert delivered["deliveries"][0]["change_id"] == cid
    assert delivered["deliveries"][0]["status"] == "offered"
    with pytest.raises(instructions.InstructionInvalid, match="do not match"):
        await instructions.deliver(other, "after", "codex", "/repo")
    with pytest.raises(instructions.InstructionInvalid, match="do not match"):
        await instructions.deliver(user, "after", "codex", "/another-repo")


async def test_rollback_changes_future_sessions_but_resume_retains_exact_snapshot(client, pool):
    user = await owner(client)
    gid = await grader(pool, user)
    v1 = await change(pool, user, gid, "Instruction one.\n")
    await instructions.release_instruction(user, v1)
    await session(user, "old-run")
    original = await instructions.deliver(user, "old-run", "codex", "/repo")
    v2 = await change(pool, user, gid, "Instruction two.", parent=v1)
    await instructions.release_instruction(user, v2)
    await session(user, "v2-run")
    second = await instructions.deliver(user, "v2-run", "codex", "/repo")
    assert second["deliveries"][0]["change_id"] == v2
    await instructions.rollback(user, gid, v1)
    assert await instructions.deliver(user, "old-run", "codex", "/repo") == original
    assert await instructions.deliver(user, "v2-run", "codex", "/repo") == second
    await session(user, "after-rollback")
    restored = await instructions.deliver(user, "after-rollback", "codex", "/repo")
    assert restored["deliveries"][0]["content"] == "Instruction one.\n"
    await instructions.rollback(user, gid, None)
    await session(user, "disabled")
    assert (await instructions.deliver(user, "disabled", "codex", "/repo"))["deliveries"] == []
    assert await instructions.deliver(user, "old-run", "codex", "/repo") == original
    assert [r["action"] for r in await instructions.list_releases(user, gid)] == [
        "disable",
        "rollback",
        "release",
        "release",
    ]


async def test_stale_draft_cannot_replace_concurrently_released_instruction(client, pool):
    user = await owner(client)
    gid = await grader(pool, user)
    a = await change(pool, user, gid, "First candidate")
    b = await change(pool, user, gid, "Concurrent candidate")
    await instructions.release_instruction(user, a)
    with pytest.raises(instructions.InstructionInvalid, match="Active instructions changed"):
        await instructions.release_instruction(user, b)
    assert await instructions.get_head(user, gid) == a


@pytest.mark.parametrize(
    "report", [None, {"passed": False}, {"passed": "false"}, {"quality_measured": False}]
)
async def test_checked_status_without_passed_checks_cannot_release(client, pool, report):
    user = await owner(client)
    gid = await grader(pool, user)
    cid = await change(pool, user, gid)
    await pool.execute("UPDATE rm_wb_changes SET check_report=$2 WHERE id=$1", cid, report)
    with pytest.raises(instructions.InstructionInvalid, match="checks must pass"):
        await instructions.release_instruction(user, cid)
    assert await instructions.get_head(user, gid) is None


async def test_harness_repository_scope_and_release_snapshot_are_respected(client, pool):
    user = await owner(client)
    gid = await grader(pool, user)
    cid = await change(pool, user, gid)
    await instructions.release_instruction(user, cid)
    await pool.execute(
        "UPDATE rm_wb_graders SET scope=$2 WHERE id=$1", gid, {"repository": "/other"}
    )
    await session(user, "claude")
    await session(user, "other-repo", "/other")
    assert (await instructions.deliver(user, "claude", "claude_code", "/repo"))["deliveries"] == []
    assert (await instructions.deliver(user, "other-repo", "codex", "/other"))["deliveries"] == []
    await session(user, "matching")
    assert len((await instructions.deliver(user, "matching", "codex", "/repo"))["deliveries"]) == 1


def native_transcript(session_id, messages, source_format="codex"):
    import json

    if source_format == "claude_code":
        return "\n".join(
            json.dumps(
                {
                    "sessionId": session_id,
                    "cwd": "/repo",
                    "type": "user" if role == "developer" else role,
                    "isMeta": role == "developer",
                    "message": {"role": "user" if role == "developer" else role, "content": text},
                }
            )
            for role, text in messages
        ).encode()

    records = [{"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}}]
    records.extend(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": text}],
            },
        }
        for role, text in messages
    )
    return "\n".join(json.dumps(row) for row in records).encode()


@pytest.mark.parametrize("source_format", ["codex", "claude_code"])
async def test_load_requires_exact_context_in_same_native_session_not_model_claim(
    client, pool, source_format
):
    user, other = await owner(client), await owner(client)
    gid = await grader(pool, user, {"source_format": source_format, "repository": "/repo"})
    cid = await change(pool, user, gid, "Keep zero valid.\nVerify the boundary test.")
    await instructions.release_instruction(user, cid)
    await session(user, "run")
    offer = await instructions.deliver(user, "run", source_format, "/repo")
    context = instruction_context(offer["deliveries"][0])
    messages = [("user", "Fix the parser."), ("assistant", context)]
    synced = await session_ingest.sync_transcript(
        user, "run", native_transcript("run", messages, source_format)
    )
    tid = UUID(str(synced["id"]))
    assert await instructions.observe_trace(user, "run", tid) == 0
    assert (await instructions.list_deliveries(user, tid))[0]["status"] == "offered"
    # A truncated/modified copy and another owner's session do not establish a receipt.
    messages += [("developer", context.replace("Keep zero valid.", "Keep zero invalid."))]
    await session_ingest.sync_transcript(
        user, "run", native_transcript("run", messages, source_format)
    )
    assert await instructions.observe_trace(user, "run", tid) == 0
    foreign = await session_ingest.sync_transcript(
        other,
        "run",
        native_transcript("run", [("developer", context), ("user", "Fix it.")], source_format),
    )
    assert await instructions.observe_trace(user, "run", UUID(str(foreign["id"]))) == 0
    messages += [("developer", context)]
    await session_ingest.sync_transcript(
        user, "run", native_transcript("run", messages, source_format)
    )
    assert await instructions.observe_trace(user, "run", tid) == 1
    assert await instructions.observe_trace(user, "run", tid) == 0
    receipt = (await instructions.list_deliveries(user, tid))[0]
    assert receipt["status"] == "captured"
    assert receipt["change_id"] == cid and receipt["trace_id"] == tid
    step = await pool.fetchrow("SELECT * FROM rm_trace_steps WHERE id=$1", receipt["step_id"])
    assert step["role"] == "system" and step["content"] == context
