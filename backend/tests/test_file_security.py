import uuid

import pytest
from httpx import AsyncClient

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

    monkeypatch.setattr(storage_service, "download_file", fail_download)
    resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/download",
        headers=_auth(api_key),
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "File storage download failed"
    assert "stash-prod" not in resp.text
    assert "secret-value" not in resp.text


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

    monkeypatch.setattr(storage_service, "download_file", fail_download)
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/ingest-csv",
        headers=_auth(api_key),
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "File storage download failed"
    assert "stash-prod" not in resp.text
    assert "secret-value" not in resp.text


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

    monkeypatch.setattr(storage_service, "download_file", download_invalid_workbook)
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/files/{file_id}/ingest-xlsx",
        headers=_auth(api_key),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Could not read workbook"
    assert "secret worksheet metadata" not in resp.text


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
    svg_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/files/{svg_id}/download",
        headers=_auth(api_key),
    )
    png_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/files/{png_id}/download",
        headers=_auth(api_key),
    )

    assert svg_resp.status_code == 200
    assert svg_resp.headers["content-disposition"].startswith("attachment;")
    assert png_resp.headers["content-disposition"].startswith("inline;")
