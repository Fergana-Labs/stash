"""Checkpoint profiles and the old reward workflow use the real API/database."""

from uuid import UUID

from backend.services.rm import workbench_auto
from backend.tasks import reward_models as rm_tasks

from .test_rm_workbench import BASE, account, upload
from .test_rm_workbench import (
    model_and_queue_boundaries as model_and_queue_boundaries,  # noqa: F401
)

CHECKPOINT = "floodgate-2026-10-05"


async def checkpoint_account(client, pool):
    user = await account(client)
    await pool.execute(
        "UPDATE users SET product_checkpoint=$2 WHERE id=$1", user["uuid"], CHECKPOINT
    )
    return user


async def test_checkpoint_defaults_to_latest_and_is_operator_managed(client, pool):
    user = await account(client)
    profile = await client.get("/api/v1/users/me", headers=user["headers"])
    assert profile.json()["product_checkpoint"] == "latest"
    edited = await client.patch(
        "/api/v1/users/me",
        headers=user["headers"],
        json={"display_name": "Sam", "product_checkpoint": CHECKPOINT},
    )
    assert edited.status_code == 200
    assert edited.json()["product_checkpoint"] == "latest"
    await pool.execute(
        "UPDATE users SET product_checkpoint=$2 WHERE id=$1", user["uuid"], CHECKPOINT
    )
    for changes in ({}, {"display_name": "Samuel"}):
        edited = await client.patch("/api/v1/users/me", headers=user["headers"], json=changes)
        assert edited.status_code == 200
        assert edited.json()["product_checkpoint"] == CHECKPOINT
    profile = await client.get("/api/v1/users/me", headers=user["headers"])
    assert profile.json()["product_checkpoint"] == CHECKPOINT
    assert profile.json()["reward_models_enabled"] is True


async def test_checkpoint_retains_traces_and_comments_without_new_workbench(client, pool):
    user = await checkpoint_account(client, pool)
    tid = await upload(client, user)
    await workbench_auto.process_trace(tid)
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_evaluations") == 0
    assert (await client.get("/api/v1/rm/traces", headers=user["headers"])).json()["total"] == 1
    detail = await client.get(f"/api/v1/rm/traces/{tid}", headers=user["headers"])
    assert detail.status_code == 200
    step_id = detail.json()["steps"][-1]["id"]
    annotation = await client.post(
        f"/api/v1/rm/traces/{tid}/annotations",
        headers=user["headers"],
        json={"step_id": step_id, "comment": "Verify the failing test."},
    )
    assert annotation.status_code == 200
    assert await pool.fetchval("SELECT count(*) FROM rm_annotations") == 1
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_feedback") == 0
    for path in (f"{BASE}/traces/{tid}/evaluation", f"{BASE}/graders"):
        assert (await client.get(path, headers=user["headers"])).status_code == 404
    assert (
        await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    ).status_code == 404


async def test_checkpoint_accepts_original_single_trace_training_request(client, pool, monkeypatch):
    user = await checkpoint_account(client, pool)
    tid = await upload(client, user)
    queued = []
    monkeypatch.setenv("RM_COMPUTE", "modal")
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", lambda mid: queued.append(mid))
    response = await client.post(
        "/api/v1/rm/reward-models",
        headers=user["headers"],
        json={"name": "Floodgate model", "trace_ids": [str(tid)]},
    )
    assert response.status_code == 200, response.text
    mid = response.json()["id"]
    assert queued == [mid]
    row = await pool.fetchrow("SELECT * FROM rm_reward_models WHERE id=$1", UUID(mid))
    assert row["training_config"] is None
    assert row["trace_ids"] == [tid]
