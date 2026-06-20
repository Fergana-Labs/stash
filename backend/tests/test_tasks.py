import uuid
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.routers import exports as exports_router
from backend.routers import tasks as tasks_router
from backend.services import source_service, task_service

from .conftest import unique_name


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> tuple[str, dict]:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("task"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    body = response.json()
    return body["api_key"], body


def _mock_success_result(monkeypatch: pytest.MonkeyPatch, result: dict) -> list[str]:
    calls = []

    def fake_async_result(task_id: str):
        calls.append(task_id)
        return SimpleNamespace(state="SUCCESS", result=result)

    monkeypatch.setattr(tasks_router.celery, "AsyncResult", fake_async_result)
    return calls


def _mock_failure_result(monkeypatch: pytest.MonkeyPatch, result: Exception) -> list[str]:
    calls = []

    def fake_async_result(task_id: str):
        calls.append(task_id)
        return SimpleNamespace(state="FAILURE", result=result)

    monkeypatch.setattr(tasks_router.celery, "AsyncResult", fake_async_result)
    return calls


@pytest.mark.asyncio
async def test_task_status_requires_task_owner(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    owner_key, owner = await _register(client)
    stranger_key, _ = await _register(client)
    task_id = "task-owned"
    await task_service.register_task(
        task_id=task_id,
        user_id=UUID(owner["id"]),
        owner_user_id=None,
        task_type="test",
    )
    calls = _mock_success_result(monkeypatch, {"download_url": "https://example.test/file"})

    owner_response = await client.get(f"/api/v1/tasks/{task_id}", headers=_auth(owner_key))
    stranger_response = await client.get(f"/api/v1/tasks/{task_id}", headers=_auth(stranger_key))
    unknown_response = await client.get("/api/v1/tasks/missing-task", headers=_auth(owner_key))

    assert owner_response.status_code == 200
    assert owner_response.json()["result"] == {"download_url": "https://example.test/file"}
    assert stranger_response.status_code == 404
    assert unknown_response.status_code == 404
    assert calls == [task_id]


@pytest.mark.asyncio
async def test_task_failure_errors_are_redacted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    owner_key, owner = await _register(client)
    task_id = "task-failed"
    await task_service.register_task(
        task_id=task_id,
        user_id=UUID(owner["id"]),
        owner_user_id=None,
        task_type="test",
    )
    calls = _mock_failure_result(
        monkeypatch,
        RuntimeError("token=secret-token and customer transcript"),
    )

    response = await client.get(f"/api/v1/tasks/{task_id}", headers=_auth(owner_key))

    assert response.status_code == 200
    assert response.json() == {
        "task_id": task_id,
        "state": "FAILURE",
        "result": None,
        "error": "Task failed",
    }
    assert "secret-token" not in response.text
    assert "customer transcript" not in response.text
    assert calls == [task_id]


@pytest.mark.asyncio
async def test_export_registers_user_owned_task(
    client: AsyncClient,
    pool,
    monkeypatch: pytest.MonkeyPatch,
):
    owner_key, owner = await _register(client)
    owner_user_id = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    page = (
        await client.post(
            f"/api/v1/workspaces/{owner_user_id}/pages/new",
            json={
                "name": "Deck",
                "content_type": "html",
                "content_html": "<section class='slide'>Demo</section>",
                "html_layout": "fixed-aspect",
            },
            headers=_auth(owner_key),
        )
    ).json()
    sent = []

    def fake_send_task(name, kwargs, task_id):
        sent.append({"name": name, "kwargs": kwargs, "task_id": task_id})

    monkeypatch.setattr(exports_router.celery, "send_task", fake_send_task)

    response = await client.post(
        f"/api/v1/pages/{page['id']}/export",
        json={"format": "pdf"},
        headers=_auth(owner_key),
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    assert sent == [
        {
            "name": "backend.exports.pdf.export_pdf",
            "kwargs": {"user_id": owner["id"], "page_id": page["id"]},
            "task_id": task_id,
        }
    ]
    task_row = await pool.fetchrow("SELECT * FROM task_records WHERE task_id = $1", task_id)
    assert task_row["user_id"] == UUID(owner["id"])
    assert task_row["owner_user_id"] == UUID(owner_user_id)
    assert task_row["task_type"] == "export:pdf"
    assert task_row["object_type"] == "page"
    assert task_row["object_id"] == UUID(page["id"])


@pytest.mark.asyncio
async def test_source_sync_registers_user_owned_task(
    client: AsyncClient,
    pool,
    monkeypatch: pytest.MonkeyPatch,
):
    api_key, owner = await _register(client)
    owner_user_id = (await client.get("/api/v1/workspaces/mine", headers=_auth(api_key))).json()[
        "workspaces"
    ][0]["id"]
    source = await source_service.create_source(
        owner_user_id=UUID(owner_user_id),
        source_type="github_repo",
        external_ref=f"repo-{uuid.uuid4().hex}",
        display_name="Repo",
    )
    sent = []

    def fake_send_task(name, kwargs, task_id):
        sent.append({"name": name, "kwargs": kwargs, "task_id": task_id})

    monkeypatch.setattr("backend.routers.sources.celery.send_task", fake_send_task)

    response = await client.post(
        f"/api/v1/workspaces/{owner_user_id}/sources/{source['id']}/sync",
        headers=_auth(api_key),
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    assert sent == [
        {
            "name": "backend.tasks.sources.sync_source",
            "kwargs": {"source_id": str(source["id"])},
            "task_id": task_id,
        }
    ]
    task_row = await pool.fetchrow("SELECT * FROM task_records WHERE task_id = $1", task_id)
    assert task_row["user_id"] == UUID(owner["id"])
    assert task_row["owner_user_id"] == UUID(owner_user_id)
    assert task_row["task_type"] == "source_sync"
    assert task_row["object_type"] == "source"
    assert task_row["object_id"] == UUID(source["id"])
