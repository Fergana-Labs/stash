"""Local fixtures must preserve grading evidence and never write to their source."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from scripts.local_trace_data import copy_snapshot, require_local_database

from .test_rm_workbench import model_and_queue_boundaries  # noqa: F401


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_loopback_destination(host):
    require_local_database(f"postgresql://dev:password@{host}:55433/local")


@pytest.mark.parametrize("url", ["postgresql://prod.example.com/stash", "postgresql:///stash"])
def test_remote_or_implicit_destination_is_rejected(url):
    with pytest.raises(ValueError, match="loopback"):
        require_local_database(url)


@asynccontextmanager
async def transaction(**kwargs):
    yield


def connections():
    source = Mock(
        transaction=Mock(side_effect=transaction), fetchrow=AsyncMock(), fetch=AsyncMock()
    )
    local = Mock(
        transaction=Mock(side_effect=transaction),
        fetchval=AsyncMock(return_value=None),
        execute=AsyncMock(),
    )
    return local, source


async def test_snapshot_preserves_ids_and_immutable_evidence_with_saved_grades():
    local, source = connections()
    trace_id, step_id, evaluation_id, call_id, owner, local_owner = (uuid4() for _ in range(6))
    trace = dict(id=trace_id, owner_user_id=owner, external_id="session", source_format="codex")
    event = dict(id=str(step_id), content="Tests pass", role="assistant")
    request = {"provider_request": {"context": [event]}, "input_hash": "saved-request-hash"}
    source.fetchrow.return_value = trace
    source.fetch.side_effect = [
        [dict(id=step_id, trace_id=trace_id, content="Tests pass")],
        [
            dict(
                id=evaluation_id,
                trace_id=trace_id,
                owner_user_id=owner,
                trace_snapshot=[event],
                revision_hash="saved-revision",
            )
        ],
        [dict(id=call_id, evaluation_id=evaluation_id, input_snapshot=request)],
    ]
    result = await copy_snapshot(local, source, owner, trace_id, local_owner)
    assert result == {"steps": 1, "evaluations": 1, "calls": 1}
    source.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
    assert source.fetchrow.call_args.args[1:] == (trace_id, owner)
    writes = local.execute.call_args_list
    assert writes[0].args[1:] == (trace_id, local_owner, "session", "codex")
    assert writes[1].args[1:] == (step_id, trace_id, "Tests pass")
    assert writes[2].args[1:] == (evaluation_id, trace_id, local_owner, [event], "saved-revision")
    assert writes[3].args[1:] == (call_id, evaluation_id, request)


async def test_snapshot_refuses_to_overwrite_a_fresh_import_or_local_edits():
    local, source = connections()
    trace_id, owner, local_owner = (uuid4() for _ in range(3))
    source.fetchrow.return_value = dict(
        id=trace_id, external_id="same-session", source_format="codex"
    )
    source.fetch.side_effect = [[], [], []]
    local.fetchval.return_value = 1
    with pytest.raises(ValueError, match="already exists"):
        await copy_snapshot(local, source, owner, trace_id, local_owner)
    local.execute.assert_not_called()


async def test_snapshot_checks_source_ownership_before_reading_evidence():
    local, source = connections()
    source.fetchrow.return_value = None
    with pytest.raises(ValueError, match="specified owner"):
        await copy_snapshot(local, source, uuid4(), uuid4(), uuid4())
    source.fetch.assert_not_called()
    local.execute.assert_not_called()


async def test_local_worker_repairs_size_rejections_without_touching_other_jobs(client, pool):
    from scripts.local_trace_data import reserve_next_trace

    from .test_rm_workbench import account, upload

    owner, other = await account(client), await account(client)
    failed = await upload(client, owner, "old-limit")
    running = await upload(client, owner, "already-running")
    foreign = await upload(client, other, "another-owner")
    reason = "The trace is 240,479 characters; automatic annotation handles up to 200,000."
    await pool.execute(
        "UPDATE rm_wb_queue SET status='failed',error=$2,attempts=3 WHERE trace_id=ANY($1::uuid[])",
        [failed, foreign],
        reason,
    )
    await pool.execute("UPDATE rm_wb_queue SET status='running' WHERE trace_id=$1", running)
    untouched = [
        dict(row)
        for row in await pool.fetch(
            "SELECT * FROM rm_wb_queue WHERE trace_id=ANY($1::uuid[]) ORDER BY trace_id",
            [running, foreign],
        )
    ]

    assert await reserve_next_trace(pool, owner["uuid"]) == failed
    repaired = await pool.fetchrow(
        "SELECT status,error,attempts,due_at>now() AS reserved FROM rm_wb_queue WHERE trace_id=$1",
        failed,
    )
    assert dict(repaired) == {"status": "queued", "error": None, "attempts": 0, "reserved": True}
    assert await reserve_next_trace(pool, owner["uuid"]) is None
    assert [
        dict(row)
        for row in await pool.fetch(
            "SELECT * FROM rm_wb_queue WHERE trace_id=ANY($1::uuid[]) ORDER BY trace_id",
            [running, foreign],
        )
    ] == untouched

    # A worker that stops between reservation and processing does not strand it.
    await pool.execute(
        "UPDATE rm_wb_queue SET due_at=now()-interval '1 second' WHERE trace_id=$1", failed
    )
    assert await reserve_next_trace(pool, owner["uuid"]) == failed
