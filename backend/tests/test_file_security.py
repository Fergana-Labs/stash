import uuid

import pytest
from httpx import AsyncClient

from backend.routers import files as files_router
from backend.services import storage_service

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("file_sec"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _workspace_id(client: AsyncClient, api_key: str) -> uuid.UUID:
    resp = await client.get("/api/v1/workspaces/mine", headers=_auth(api_key))
    assert resp.status_code == 200
    return uuid.UUID(resp.json()["workspaces"][0]["id"])


async def _make_file(
    pool,
    *,
    workspace_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    name: str,
    content_type: str,
) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, 12, $4, $5) RETURNING id",
        workspace_id,
        name,
        content_type,
        f"customer/webflow/{uuid.uuid4().hex}",
        uploaded_by,
    )


@pytest.mark.asyncio
async def test_file_download_storage_errors_are_redacted(client: AsyncClient, pool, monkeypatch):
    api_key, owner = await _register(client)
    workspace_id = await _workspace_id(client, api_key)
    file_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="board-notes.txt",
        content_type="text/plain",
    )

    async def fail_download(storage_key):
        raise RuntimeError(f"bucket=stash-prod key={storage_key} token=secret-value")

    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(storage_service, "download_file", fail_download)
    monkeypatch.setattr(files_router.logger, "warning", capture_warning)
    resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/download",
        headers=_auth(api_key),
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "File storage download failed"
    assert "stash-prod" not in resp.text
    assert "secret-value" not in resp.text
    assert captured_logs == [
        (
            "file storage download failed operation=%s exception_type=%s",
            ("file download", "RuntimeError"),
            {},
        )
    ]
    assert "customer/webflow" not in str(captured_logs)
    assert "secret-value" not in str(captured_logs)


@pytest.mark.asyncio
async def test_file_ingest_storage_errors_are_redacted(client: AsyncClient, pool, monkeypatch):
    api_key, owner = await _register(client)
    workspace_id = await _workspace_id(client, api_key)
    file_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="pipeline.csv",
        content_type="text/csv",
    )

    async def fail_download(storage_key):
        raise RuntimeError(f"bucket=stash-prod key={storage_key} token=secret-value")

    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(storage_service, "download_file", fail_download)
    monkeypatch.setattr(files_router.logger, "warning", capture_warning)
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/ingest-csv",
        headers=_auth(api_key),
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "File storage download failed"
    assert "stash-prod" not in resp.text
    assert "secret-value" not in resp.text
    assert captured_logs == [
        (
            "file storage download failed operation=%s exception_type=%s",
            ("csv ingest", "RuntimeError"),
            {},
        )
    ]
    assert "customer/webflow" not in str(captured_logs)
    assert "secret-value" not in str(captured_logs)


@pytest.mark.asyncio
async def test_xlsx_parse_errors_are_redacted(client: AsyncClient, pool, monkeypatch):
    api_key, owner = await _register(client)
    workspace_id = await _workspace_id(client, api_key)
    file_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="pipeline.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    async def download_invalid_workbook(storage_key):
        return b"not an xlsx containing secret worksheet metadata"

    async def fail_ingest_xlsx_bytes(**kwargs):
        raise RuntimeError("secret worksheet metadata from workbook parser")

    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(storage_service, "download_file", download_invalid_workbook)
    monkeypatch.setattr(files_router, "ingest_xlsx_bytes", fail_ingest_xlsx_bytes)
    monkeypatch.setattr(files_router.logger, "warning", capture_warning)
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/ingest-xlsx",
        headers=_auth(api_key),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Could not read workbook"
    assert "secret worksheet metadata" not in resp.text
    assert captured_logs == [
        (
            "xlsx ingest failed file_id=%s exception_type=%s",
            (file_id, "RuntimeError"),
            {},
        )
    ]
    assert "secret worksheet metadata" not in str(captured_logs)


@pytest.mark.asyncio
async def test_svg_downloads_as_attachment_not_inline(client: AsyncClient, pool, monkeypatch):
    """SVG executes embedded script when rendered inline, so user uploads must
    never come back inline on the API origin; passive image types stay inline."""
    api_key, owner = await _register(client)
    workspace_id = await _workspace_id(client, api_key)
    svg_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="logo.svg",
        content_type="image/svg+xml",
    )
    # content_type is attacker-controlled; parameter and case variants must not
    # bypass the SVG attachment rule.
    svg_charset_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="logo2.svg",
        content_type="image/svg+xml;charset=utf-8",
    )
    svg_upper_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="logo3.svg",
        content_type="image/SVG+xml",
    )
    png_id = await _make_file(
        pool,
        workspace_id=workspace_id,
        uploaded_by=uuid.UUID(owner["id"]),
        name="logo.png",
        content_type="image/png",
    )

    async def fake_download(storage_key):
        return b'<svg onload="alert(1)"/>'

    monkeypatch.setattr(storage_service, "download_file", fake_download)

    async def download(file_id):
        return await client.get(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}/download",
            headers=_auth(api_key),
        )

    svg_resp = await download(svg_id)
    svg_charset_resp = await download(svg_charset_id)
    svg_upper_resp = await download(svg_upper_id)
    png_resp = await download(png_id)

    assert svg_resp.status_code == 200
    assert svg_resp.headers["content-disposition"].startswith("attachment;")
    assert svg_charset_resp.headers["content-disposition"].startswith("attachment;")
    assert svg_upper_resp.headers["content-disposition"].startswith("attachment;")
    assert png_resp.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_file_purge_keeps_storage_keys_still_referenced(
    client: AsyncClient, pool, monkeypatch
):
    """Forks copy storage_key by reference (shared_skill_service._fork_file),
    so purging the origin file must not delete an S3 object a surviving fork
    still serves downloads from. Unreferenced keys are still deleted."""
    api_key, owner = await _register(client)
    workspace_id = await _workspace_id(client, api_key)
    owner_id = uuid.UUID(owner["id"])

    async def insert_file(name: str, storage_key: str) -> uuid.UUID:
        return await pool.fetchval(
            "INSERT INTO files "
            "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
            "VALUES ($1, $2, 'text/plain', 12, $3, $4) RETURNING id",
            workspace_id,
            name,
            storage_key,
            owner_id,
        )

    shared_id = await insert_file("origin.txt", "shared-fork-key")
    await insert_file("forked-copy.txt", "shared-fork-key")
    unique_id = await insert_file("unique.txt", "unique-file-key")

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_keys.append(storage_key)

    monkeypatch.setattr(files_router.storage_service, "delete_file", fake_delete_file)

    for file_id in (shared_id, unique_id):
        trashed = await client.delete(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}",
            headers=_auth(api_key),
        )
        assert trashed.status_code == 204
        purged = await client.delete(
            f"/api/v1/workspaces/{workspace_id}/files/{file_id}/purge",
            headers=_auth(api_key),
        )
        assert purged.status_code == 204

    assert deleted_keys == ["unique-file-key"]
    fork_count = await pool.fetchval(
        "SELECT COUNT(*) FROM files WHERE storage_key = 'shared-fork-key'"
    )
    assert fork_count == 1
