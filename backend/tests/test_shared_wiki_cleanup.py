"""Cleanup preserves originals and publishes only independently reviewed revisions."""

import json

import pytest

from backend.services import shared_wiki_cleanup as cleanup
from backend.services import shared_wiki_privacy as privacy

from .test_scoped_curation import dataset as dataset
from .test_scoped_curation import scope


async def original(pool, data):
    _, pages = await cleanup.snapshot(
        pool, data.workspace["id"], data.owner, data.workspace["external_wiki_folder_id"]
    )
    return next(p for p in pages if p["id"] == data.shared)


def completions(monkeypatch, *, approved=True, publishable=True, before_review=None):
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        if kwargs["output_model"] is cleanup.Candidate:
            if before_review:
                await before_review()
            return cleanup.Candidate(
                publishable=publishable,
                title="Filter selection",
                content="Confirm the application.",
            )
        return privacy.PrivacyReview(approved=approved, issues=[] if approved else ["unsafe"])

    monkeypatch.setattr(cleanup.llm, "complete_structured", complete)
    return calls


@pytest.mark.asyncio
async def test_cleanup_archives_original_and_publishes_exact_reviewed_text(
    dataset, pool, monkeypatch
):
    source = await original(pool, dataset)
    calls = completions(monkeypatch)
    result = await cleanup.clean_page(pool, dataset.workspace, source)
    assert result["status"] == "published" and len(calls) == 2
    reviewed = json.loads(calls[1]["prompt"])
    assert reviewed["private_source_for_faithfulness_check"]["body"] == source["content_markdown"]
    archived = await pool.fetchval(
        "SELECT original FROM shared_wiki_originals WHERE page_id=$1", dataset.shared
    )
    assert archived == cleanup.source_record(source)
    published = await privacy.published_pages(pool, dataset.workspace["id"], dataset.shared)
    assert published[0]["name"] == reviewed["title"] == "Filter selection"
    assert published[0]["content_markdown"] == reviewed["body"] == "Confirm the application."
    row = await pool.fetchrow(
        "SELECT embed_stale,embedding,metadata FROM pages WHERE id=$1", dataset.shared
    )
    assert row["embed_stale"] and row["embedding"] is None and row["metadata"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("publishable,approved", [(False, True), (True, False)])
async def test_unusable_or_rejected_candidate_stays_quarantined(
    dataset, pool, monkeypatch, publishable, approved
):
    source = await original(pool, dataset)
    completions(monkeypatch, publishable=publishable, approved=approved)
    result = await cleanup.clean_page(pool, dataset.workspace, source)
    assert result["status"] == "quarantined"
    assert cleanup.fingerprint(await original(pool, dataset)) == cleanup.fingerprint(source)
    assert not await privacy.published_pages(pool, dataset.workspace["id"])


@pytest.mark.asyncio
async def test_cleanup_does_not_overwrite_concurrent_edit(dataset, pool, monkeypatch):
    source = await original(pool, dataset)

    async def edit():
        await pool.execute(
            "UPDATE pages SET content_markdown='New evidence' WHERE id=$1", dataset.shared
        )

    completions(monkeypatch, before_review=edit)
    result = await cleanup.clean_page(pool, dataset.workspace, source)
    assert result["reason"] == "source_changed"
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "New evidence"
    )
    assert not await privacy.published_pages(pool, dataset.workspace["id"])


@pytest.mark.asyncio
async def test_cleanup_rechecks_permissions_before_commit(dataset, pool, monkeypatch):
    source = await original(pool, dataset)

    async def revoke():
        await pool.execute(
            "UPDATE workspaces SET curation_generation=curation_generation+1 WHERE id=$1",
            dataset.workspace["id"],
        )

    completions(monkeypatch, before_review=revoke)
    with pytest.raises(PermissionError, match="permissions changed"):
        await cleanup.clean_page(pool, dataset.workspace, source)
    assert not await pool.fetchval(
        "SELECT 1 FROM shared_wiki_originals WHERE page_id=$1", dataset.shared
    )


@pytest.mark.asyncio
async def test_cleanup_does_not_repeat_approved_pages(dataset, pool, monkeypatch):
    await scope(dataset, "shared")
    calls = completions(monkeypatch)
    result = await cleanup.clean_page(pool, dataset.workspace, await original(pool, dataset))
    assert result["status"] == "already_approved" and not calls


@pytest.mark.asyncio
async def test_manifest_binds_exact_original_and_scope(dataset, pool):
    source = await original(pool, dataset)
    assert cleanup.manifest_hash([source]) != cleanup.manifest_hash([{**source, "name": "Changed"}])
    with pytest.raises(ValueError, match="scope"):
        await cleanup.snapshot(
            pool, dataset.workspace["id"], dataset.owner, dataset.users["private"]["wiki_folder_id"]
        )


@pytest.mark.asyncio
async def test_index_is_rebuilt_only_from_approved_pages(dataset, pool, monkeypatch):
    shared = await scope(dataset, "shared")
    lesson = await shared.tool(
        "write_page",
        {
            "page_id": None,
            "title": "Public part lesson",
            "content": "Confirm the application.",
        },
    )
    await pool.execute("DELETE FROM shared_wiki_reviews WHERE page_id=$1", dataset.shared)
    calls = completions(monkeypatch)
    result = await cleanup.clean_page(
        pool, dataset.workspace, await original(pool, dataset), refresh_index=True
    )
    assert result["status"] == "published" and len(calls) == 1
    body = await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
    assert body == f"- [Public part lesson](/p/{lesson['page_id']})"
    assert (
        "reviewed_page_catalogue"
        in json.loads(calls[0]["prompt"])["private_source_for_faithfulness_check"]
    )
