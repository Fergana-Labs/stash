"""Automatic recovery obeys the same account gate as the trace worker."""

from uuid import UUID

import pytest

from backend.services.rm import workbench_auto as auto

from .test_rm_workbench import BASE, account, model_and_queue_boundaries, upload  # noqa: F401


@pytest.mark.parametrize("checkpoint", ["floodgate-2026-10-05", "disabled"])
@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("completed", None),
        ("failed", auto.SCHEMA_CACHE_ERROR),
        ("failed", "TYPESAFE_API_KEY is not configured"),
        ("queued", "Daily Jev evaluation budget reached; resumes tomorrow"),
    ],
)
async def test_queue_recovery_preserves_gated_accounts(
    client, pool, monkeypatch, checkpoint, status, error
):
    monkeypatch.setattr(auto.settings, "TYPESAFE_API_KEY", "test-key")
    latest = await account(client)
    protected = await account(client)
    active_trace = await upload(client, latest, "active")
    protected_trace = await upload(client, protected, "protected")
    await pool.execute(
        "UPDATE users SET product_checkpoint=$2,reward_models_enabled=$3 WHERE id=$1",
        protected["uuid"],
        "latest" if checkpoint == "disabled" else checkpoint,
        checkpoint != "disabled",
    )
    await pool.execute(
        """UPDATE rm_wb_queue SET status=$2,error=$3,attempts=1,
        due_at=now()+interval '1 day' WHERE trace_id=ANY($1::uuid[])""",
        [active_trace, protected_trace],
        status,
        error,
    )
    before = dict(
        await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", protected_trace)
    )

    await auto.recover()

    assert (
        dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", protected_trace))
        == before
    )
    repaired = await pool.fetchrow(
        "SELECT status,due_at<=now() AS ready FROM rm_wb_queue WHERE trace_id=$1", active_trace
    )
    assert dict(repaired) == {"status": "queued", "ready": True}


@pytest.mark.parametrize("checkpoint", ["floodgate-2026-10-05", "disabled"])
async def test_feedback_recovery_preserves_gated_accounts(client, pool, checkpoint):
    latest = await account(client)
    protected = await account(client)
    feedback_ids = []
    for user in (latest, protected):
        trace_id = await upload(client, user)
        response = await client.post(
            f"{BASE}/feedback",
            headers=user["headers"],
            json={"trace_id": str(trace_id), "comment": "Verify tests before claiming success."},
        )
        assert response.status_code == 201, response.text
        feedback_ids.append(UUID(response.json()["id"]))
    await pool.execute(
        "UPDATE users SET product_checkpoint=$2,reward_models_enabled=$3 WHERE id=$1",
        protected["uuid"],
        "latest" if checkpoint == "disabled" else checkpoint,
        checkpoint != "disabled",
    )
    await pool.execute(
        "UPDATE rm_wb_feedback SET status='failed',error=$2 WHERE id=ANY($1::uuid[])",
        feedback_ids,
        auto.MISSING_REPOSITORY,
    )
    before = dict(await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", feedback_ids[1]))

    await auto.recover()

    assert (
        dict(await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", feedback_ids[1]))
        == before
    )
    repaired = await pool.fetchrow(
        "SELECT status,error FROM rm_wb_feedback WHERE id=$1", feedback_ids[0]
    )
    assert dict(repaired) == {"status": "queued", "error": None}
