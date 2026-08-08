"""The sweep mirrors the provider; the wipe protection lives at the boundary.

Policy across every integration: believe a listing the indexer could read (even
an empty one) and mirror it, but never let a malformed or truncated response
reach the sweep. `remove_missing_documents` is a dumb mirror — an empty listing
deletes — and `expect_items` is the gate that fails loud on a response we could
not read, before any deletion. (Granola additionally cross-checks the count on
its own envelope; other providers use `expect_items`.)
"""

from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import source_service
from backend.services.source_service import SourceSyncUserError, expect_items


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


# --- expect_items: the boundary gate ---------------------------------------


def test_expect_items_returns_a_present_list_including_empty():
    assert expect_items({"files": ["a", "b"]}, "files", provider="Drive") == ["a", "b"]
    # A present-but-empty list is a believed empty result, not an error.
    assert expect_items({"files": []}, "files", provider="Drive") == []


@pytest.mark.parametrize(
    "payload",
    [
        {},  # container key absent — malformed, not empty
        {"files": None},  # null where a list was expected
        {"files": {"nope": 1}},  # wrong type
        "a string, not a dict",
        None,
    ],
)
def test_expect_items_raises_on_a_response_it_cannot_read(payload):
    with pytest.raises(SourceSyncUserError, match="could not read"):
        expect_items(payload, "files", provider="Drive")


# --- remove_missing_documents: a dumb mirror -------------------------------


@pytest.mark.asyncio
async def test_empty_listing_mirrors_and_deletes(granola_source, _db_pool):
    # The indexer already vouched the empty listing is real, so the sweep mirrors
    # it: an empty present deletes everything (the account is empty).
    removed = await source_service.remove_missing_documents("granola_notes", granola_source, [])
    assert removed == 2
    kept = await _db_pool.fetchval(
        "SELECT COUNT(*) FROM granola_notes WHERE source_id = $1", granola_source
    )
    assert kept == 0


@pytest.mark.asyncio
async def test_partial_listing_prunes_only_the_missing(granola_source, _db_pool):
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
