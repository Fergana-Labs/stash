"""An empty provider listing must never delete a stored archive.

Providers return empty listings for reasons that aren't "the user deleted
everything": API contract drift, silent truncation (X bookmarks, 2026-08-06),
auth quirks that 200 with no data (Granola, 2026-08 — a month of transcripts
hard-deleted by a sync that reported success). The sweep refuses instead.
"""

from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import source_service
from backend.services.source_service import SourceSyncUserError


@pytest_asyncio.fixture
async def granola_source(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    source_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO user_sources (id, owner_user_id, source_type, external_ref, display_name) "
        "VALUES ($1, $2, 'granola', $3, 'Granola')",
        source_id,
        user_id,
        f"granola-{source_id.hex[:6]}",
    )
    for i in range(2):
        await _db_pool.execute(
            "INSERT INTO granola_notes "
            "(source_id, owner_user_id, path, name, kind, content, external_ref) "
            "VALUES ($1, $2, $3, $4, 'note', 'transcript text', $5)",
            source_id,
            user_id,
            f"2026-07/meeting-{i}",
            f"Meeting {i}",
            f"m-{i}",
        )
    return source_id


@pytest.mark.asyncio
async def test_empty_listing_refuses_to_delete_stored_docs(granola_source, _db_pool):
    with pytest.raises(SourceSyncUserError, match="Refusing to delete"):
        await source_service.remove_missing_documents("granola_notes", granola_source, [])

    kept = await _db_pool.fetchval(
        "SELECT COUNT(*) FROM granola_notes WHERE source_id = $1", granola_source
    )
    assert kept == 2


@pytest.mark.asyncio
async def test_partial_listing_still_prunes_normally(granola_source, _db_pool):
    removed = await source_service.remove_missing_documents(
        "granola_notes", granola_source, ["2026-07/meeting-0"]
    )
    assert removed == 1
    kept = await _db_pool.fetchval(
        "SELECT path FROM granola_notes WHERE source_id = $1", granola_source
    )
    assert kept == "2026-07/meeting-0"


@pytest.mark.asyncio
async def test_empty_listing_on_empty_source_is_a_no_op(_db_pool):
    assert await source_service.remove_missing_documents("granola_notes", uuid4(), []) == 0
