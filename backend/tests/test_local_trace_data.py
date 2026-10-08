"""Local fixtures must preserve grading evidence and never write to their source."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from scripts.local_trace_data import copy_snapshot, require_local_database


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
