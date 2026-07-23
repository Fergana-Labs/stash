"""Disconnect keeps data; deletion is explicit; reconnect is identity-checked.

Disconnecting an integration is a credentials operation: tokens are revoked
and nulled but the user_integrations row (carrying account_ref) and all
source rows/documents survive. A reconnect under a DIFFERENT provider
account is refused while the previous account's connection exists — kept
data must never silently continue under a new identity. The explicit purge
path is the only way data, media blobs, and share grants are removed.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet
from backend.services import source_service, user_service


@pytest.fixture
def fernet_key(monkeypatch):
    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )


@pytest.fixture
def quiet_provider(monkeypatch):
    """Providers whose revoke/refresh never leave the process."""

    async def revoke(token):
        return None

    monkeypatch.setattr(storage, "get_provider", lambda p: SimpleNamespace(revoke=revoke))


async def _user() -> UUID:
    user, _api_key = await user_service.register_user(
        name=f"retain_{uuid4().hex[:8]}",
        display_name="Retention User",
        password="securepassword1",
    )
    return user["id"]


def _token() -> TokenSet:
    return TokenSet(
        access_token="access-token",
        refresh_token=None,
        expires_at=None,
        scopes=["read"],
    )


@pytest.mark.asyncio
async def test_disconnect_stored_keeps_row_and_fails_reads_loud(
    pool, fernet_key, quiet_provider
) -> None:
    user_id = await _user()
    await storage.store_token(
        user_id, "x", _token(), AccountInfo(email=None, display_name="@sam", account_ref="111")
    )

    await storage.disconnect_stored(user_id, "x")

    # The row survives with its identity; the tokens are gone.
    row = await pool.fetchrow(
        "SELECT account_ref, access_token_encrypted FROM user_integrations "
        "WHERE user_id = $1 AND provider = 'x'",
        user_id,
    )
    assert row["account_ref"] == "111"
    assert row["access_token_encrypted"] is None

    # Reads that need the token fail loud with the disconnected message, not
    # the never-connected one.
    with pytest.raises(HTTPException) as exc:
        await storage.get_valid_token(user_id, "x")
    assert "disconnected" in exc.value.detail

    status = await storage.status(user_id, "x")
    assert status["connected"] is False
    assert status["disconnected"] is True
    assert status["accounts"][0]["needs_reconnect"] is True


@pytest.mark.asyncio
async def test_reconnect_under_a_different_account_is_refused(
    pool, fernet_key, quiet_provider
) -> None:
    user_id = await _user()
    await storage.store_token(
        user_id, "x", _token(), AccountInfo(email=None, display_name="@sam", account_ref="111")
    )
    await storage.disconnect_stored(user_id, "x")

    other = AccountInfo(email=None, display_name="@intruder", account_ref="222")
    assert await storage.account_mismatch(user_id, "x", other) == "@sam"

    same = AccountInfo(email=None, display_name="@sam", account_ref="111")
    assert await storage.account_mismatch(user_id, "x", same) is None

    # A provider that can't supply an id can't be checked — never a false block.
    unknown = AccountInfo(email=None, display_name=None, account_ref=None)
    assert await storage.account_mismatch(user_id, "x", unknown) is None


@pytest.mark.asyncio
async def test_reconnect_reenables_source_and_preserves_settings(pool) -> None:
    user_id = await _user()
    source = await source_service.create_source(
        owner_user_id=user_id,
        source_type="x_saves",
        external_ref="111",
        display_name="X",
        settings={},
    )
    source_id = UUID(source["id"])
    # The connect flow merges connect-time keys after the upsert (router.py).
    await pool.execute(
        "UPDATE user_sources SET settings = coalesce(settings, '{}'::jsonb) || "
        '\'{"x_user_id": "111"}\' WHERE id = $1',
        source_id,
    )
    # Sync state accumulated while connected (cursors, one-time-walk marks).
    await pool.execute(
        "UPDATE user_sources SET settings = settings || '{\"x_timeline_complete\": true}' "
        "WHERE id = $1",
        source_id,
    )
    await source_service.disable_sources_for_provider(user_id, "x")
    assert (
        await pool.fetchval("SELECT sync_enabled FROM user_sources WHERE id = $1", source_id)
        is False
    )

    # The connect flow runs the same create_source again.
    reconnected = await source_service.create_source(
        owner_user_id=user_id,
        source_type="x_saves",
        external_ref="111",
        display_name="X",
        settings={},
    )
    assert UUID(reconnected["id"]) == source_id  # same row, same documents
    row = await pool.fetchrow(
        "SELECT sync_enabled, settings FROM user_sources WHERE id = $1", source_id
    )
    assert row["sync_enabled"] is True
    assert row["settings"]["x_timeline_complete"] is True  # walk state survived


@pytest.mark.asyncio
async def test_per_source_delete_cleans_blobs_and_shares(pool, monkeypatch) -> None:
    # The per-source Remove button is the only delete path extension-fed
    # sources have — it must clean up exactly what the provider purge does.
    from backend.services import storage_service

    deleted_blobs: list[str] = []

    async def fake_delete_file(key):
        deleted_blobs.append(key)

    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    user_id = await _user()
    grantee_id = await _user()
    source = await source_service.create_source(
        owner_user_id=user_id,
        source_type="x_saves",
        external_ref="222",
        display_name="X",
        settings={},
    )
    source_id = UUID(source["id"])
    await pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref, media) "
        "VALUES ($1, $2, 'Bookmarks/2', '2', 'Bookmark', '2', "
        '\'[{"storage_key": "store/x-2-0.jpg", "content_type": "image/jpeg"}]\')',
        user_id,
        source_id,
    )
    await pool.execute(
        "INSERT INTO shares (owner_user_id, created_by, object_type, object_id, "
        "principal_type, principal_id, permission) "
        "VALUES ($1, $1, 'source', $2, 'user', $3, 'read')",
        user_id,
        source_id,
        grantee_id,
    )

    assert await source_service.delete_source(source_id, user_id) is True

    assert deleted_blobs == ["store/x-2-0.jpg"]
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM shares WHERE object_type = 'source' AND object_id = $1",
            source_id,
        )
        == 0
    )
    # A non-owner can't trigger the cleanup path at all.
    assert await source_service.delete_source(source_id, grantee_id) is False


@pytest.mark.asyncio
async def test_purge_deletes_documents_media_blobs_and_shares(pool, monkeypatch) -> None:
    from backend.services import storage_service

    deleted_blobs: list[str] = []

    async def fake_delete_file(key):
        deleted_blobs.append(key)

    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    user_id = await _user()
    grantee_id = await _user()
    source = await source_service.create_source(
        owner_user_id=user_id,
        source_type="x_saves",
        external_ref="111",
        display_name="X",
        settings={},
    )
    source_id = UUID(source["id"])
    await pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref, media) "
        "VALUES ($1, $2, 'Bookmarks/1', '1', 'Bookmark', '1', "
        '\'[{"storage_key": "store/x-1-0.jpg", "content_type": "image/jpeg"}]\')',
        user_id,
        source_id,
    )
    await pool.execute(
        "INSERT INTO shares (owner_user_id, created_by, object_type, object_id, "
        "principal_type, principal_id, permission) "
        "VALUES ($1, $1, 'source', $2, 'user', $3, 'read')",
        user_id,
        source_id,
        grantee_id,
    )

    purged = await source_service.purge_sources_for_provider(user_id, "x")

    assert [UUID(p["id"]) for p in purged] == [source_id]
    assert deleted_blobs == ["store/x-1-0.jpg"]
    assert (
        await pool.fetchval("SELECT count(*) FROM x_save_docs WHERE source_id = $1", source_id) == 0
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM shares WHERE object_type = 'source' AND object_id = $1",
            source_id,
        )
        == 0
    )
