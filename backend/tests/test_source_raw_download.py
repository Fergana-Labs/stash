"""Raw source-document download: the PDF itself, not its extracted text.

Vision-capable agents read documents with their own eyes; that only works if
the VFS can hand over the original bytes. These tests pin the contract: Drive-
backed documents stream verbatim from the provider, everything else refuses
loudly (a Slack thread has no original file — serving one would be invented),
and provider-side refusals (Google-native docs, oversize files) keep their
meaning as HTTP statuses instead of collapsing into a generic error.
"""

from uuid import UUID

from httpx import AsyncClient

from backend.integrations.google import indexer
from backend.services import source_service
from backend.tests.test_sources import _auth, _register


async def _drive_source_with_document(client: AsyncClient, api_key: str, owner_id: UUID) -> str:
    add = await client.post(
        "/api/v1/me/sources",
        json={
            "source_type": "google_drive",
            "external_ref": "drive-root",
            "display_name": "Drive",
        },
        headers=_auth(api_key),
    )
    assert add.status_code == 200
    source = add.json()
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(source["id"]),
        owner_user_id=owner_id,
        path="Catalogs/bendix.pdf",
        name="bendix.pdf",
        external_ref="drive-file-1",
    )
    return source["id"]


async def test_drive_document_downloads_original_bytes(client: AsyncClient, monkeypatch):
    api_key, user_id = await _register(client)
    source_id = await _drive_source_with_document(client, api_key, user_id)

    async def fake_download(owner_user_id, file_id, *, max_bytes):
        assert file_id == "drive-file-1"
        return b"%PDF-1.4 catalog bytes", "application/pdf", "bendix.pdf"

    monkeypatch.setattr(indexer, "download_drive_file", fake_download)

    resp = await client.get(
        f"/api/v1/me/sources/{source_id}/doc/raw",
        params={"ref": "Catalogs/bendix.pdf"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 catalog bytes"
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "bendix.pdf" in resp.headers["content-disposition"]


async def test_non_drive_sources_refuse_raw_download(client: AsyncClient):
    """A GitHub file, Slack thread, or Gmail message is a provider API object,
    not a file — raw download must refuse, not serve extracted text as if it
    were the original."""
    api_key, _ = await _register(client)
    add = await client.post(
        "/api/v1/me/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "acme/widgets",
            "display_name": "acme/widgets",
        },
        headers=_auth(api_key),
    )
    assert add.status_code == 200

    resp = await client.get(
        f"/api/v1/me/sources/{add.json()['id']}/doc/raw",
        params={"ref": "README.md"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 415


async def test_missing_document_is_404(client: AsyncClient):
    api_key, user_id = await _register(client)
    source_id = await _drive_source_with_document(client, api_key, user_id)

    resp = await client.get(
        f"/api/v1/me/sources/{source_id}/doc/raw",
        params={"ref": "Catalogs/nope.pdf"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 404


async def test_google_native_document_refusal_keeps_its_status(client: AsyncClient, monkeypatch):
    """A Google Doc has no original file to download. The provider-side refusal
    must reach the caller as a 415 with the reason, so an agent learns to read
    it as text instead of retrying."""
    api_key, user_id = await _register(client)
    source_id = await _drive_source_with_document(client, api_key, user_id)

    async def fake_download(owner_user_id, file_id, *, max_bytes):
        raise indexer.DriveFileUnsupported("Google-native document; read it as text")

    monkeypatch.setattr(indexer, "download_drive_file", fake_download)

    resp = await client.get(
        f"/api/v1/me/sources/{source_id}/doc/raw",
        params={"ref": "Catalogs/bendix.pdf"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 415
    assert "read it as text" in resp.json()["detail"]
