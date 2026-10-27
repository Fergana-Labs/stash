"""Customer publication must be fail-closed, including edits and metadata."""

import asyncio
import json

import pytest

from backend.services import scoped_curation_service as curation
from backend.services import shared_wiki_privacy as privacy
from backend.services import vfs_service

from .test_permissions import _auth
from .test_scoped_curation import dataset as dataset
from .test_scoped_curation import scope


@pytest.mark.parametrize(
    "text",
    [
        "VIN 1ZZZZZZZ0ZZ000001",
        "Engine ESN 99000001",
        "Job 99000002",
        "RO D-99001",
        "Unit 99003",
        "Sales order 99004",
        "Contact person@gmail.com",
        "source:raw-customer-file",
        "Session 11111111-2222-4333-8444-555555555555",
        "ＶＩＮ １ＺＺＺＺＺＺＺ０ＺＺ０００００１",
        "person\u200b@gmail.com",
        "https://example.com/?vin=1ZZZZZZZ0ZZ000001",
        "person%40gmail.com",
        "person&#64;gmail.com",
    ],
)
def test_observed_identifier_patterns_are_rejected_in_title_or_body(text):
    assert privacy.deterministic_issues(text, "Technical lesson")
    assert privacy.deterministic_issues("Index", text)


def test_public_part_facts_are_not_identifier_matches():
    assert not privacy.deterministic_issues(
        "Cummins N14 filter fitment", "Fleetguard LF667 is a filter. Confirm the application."
    )


@pytest.mark.asyncio
async def test_unreviewed_shared_is_hidden_but_private_still_readable(dataset, client, pool):
    response = await client.post(
        "/api/v1/me/vfs",
        json={"script": "grep -r . /memory /files", "user_id": "private"},
        headers=_auth(dataset.key),
    )
    assert response.status_code == 200, response.text
    assert "ALLOWED_SHARED_KNOWLEDGE" not in response.text
    assert "PRIVATE_WIKI_SECRET" in response.text
    assert "PUBLIC_WIKI_SECRET" not in response.text
    # No deletion/rewrite is involved in quarantine.
    assert await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)


@pytest.mark.asyncio
async def test_unreviewed_shared_is_not_a_curator_reference(dataset):
    raw = await curation.load_scope(
        dataset.workspace,
        "shared",
        dataset.workspace["external_wiki_folder_id"],
        [dataset.users["public"]["id"]],
        "privacy-test",
        None,
        None,
    )
    assert str(dataset.shared) not in raw.documents


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["write_page", "edit_page"])
async def test_complete_candidate_gets_independent_semantic_review(
    dataset, pool, monkeypatch, method
):
    shared = await scope(dataset, "shared")
    reviewed = []

    async def reject(**kwargs):
        reviewed.append(json.loads(kwargs["prompt"]))
        return privacy.PrivacyReview(approved=False, issues=["named_customer_transaction"])

    monkeypatch.setattr(privacy.llm, "complete_structured", reject)
    customer_text = "Anonymized fleet / Example Fleet LLC ordered a turbo."
    arguments = (
        {"page_id": str(dataset.shared), "title": "Index", "content": customer_text}
        if method == "write_page"
        else {"page_id": str(dataset.shared), "old_text": "KNOWLEDGE", "new_text": customer_text}
    )
    result = await shared.tool(method, arguments)
    assert "error" in result
    assert customer_text in reviewed[0]["body"] and reviewed[0]["title"] == "Index"
    if method == "edit_page":
        assert reviewed[0]["body"].startswith("ALLOWED_SHARED_")
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )
    assert (
        await pool.fetchval("SELECT count(*) FROM page_edits WHERE page_id=$1", dataset.shared) == 0
    )


@pytest.mark.asyncio
async def test_hard_identifier_gate_does_not_call_model(dataset, monkeypatch):
    shared = await scope(dataset, "shared")

    async def unexpected(**kwargs):
        pytest.fail("deterministic rejection must happen before model review")

    monkeypatch.setattr(privacy.llm, "complete_structured", unexpected)
    result = await shared.tool(
        "write_page",
        {
            "page_id": None,
            "title": "Index",
            "content": "VIN 1ZZZZZZZ0ZZ000001",
        },
    )
    assert "vehicle_identifier" in result["issues"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "name='Example Truck Sales'",
        "content_markdown='Customer transaction'",
        "content_type='html',content_html='Customer transaction'",
        "deleted_at=now()",
        "folder_id=NULL",
    ],
)
async def test_exact_approval_invalidates_on_change(dataset, pool, mutation):
    await scope(dataset, "shared")
    assert await privacy.customer_page(str(dataset.workspace["id"]), str(dataset.shared), None)
    await pool.execute(f"UPDATE pages SET {mutation} WHERE id=$1", dataset.shared)
    assert (
        await privacy.customer_page(str(dataset.workspace["id"]), str(dataset.shared), None) is None
    )


@pytest.mark.asyncio
async def test_stale_policy_and_forged_metadata_cannot_approve(dataset, pool):
    await pool.execute(
        "UPDATE pages SET metadata=$2 WHERE id=$1",
        dataset.shared,
        {"approved": True, "privacy_review": {"approved": True}},
    )
    assert not await privacy.published_for_workspace(str(dataset.workspace["id"]))
    await scope(dataset, "shared")
    await pool.execute(
        "UPDATE shared_wiki_reviews SET policy_version='old' WHERE page_id=$1", dataset.shared
    )
    assert not await privacy.published_for_workspace(str(dataset.workspace["id"]))


@pytest.mark.asyncio
async def test_private_provenance_metadata_not_exposed(dataset, pool):
    await scope(dataset, "shared")
    await pool.execute(
        "UPDATE pages SET metadata=$2,last_edit_session_id='private-session' WHERE id=$1",
        dataset.shared,
        {"secret": "customer@example.com"},
    )
    rows = await privacy.published_for_workspace(str(dataset.workspace["id"]))
    assert rows[0]["metadata"] == {}
    assert "private-session" not in json.dumps(rows) and "customer@example.com" not in json.dumps(
        rows
    )


@pytest.mark.asyncio
async def test_unapproved_links_rejected_including_private_pages(dataset, pool):
    for page in (dataset.shared, dataset.pages["private"]):
        result = await privacy.review(
            pool, dataset.workspace["id"], "Index", f"[Lesson](/p/{page})"
        )
        assert not result.approved and "link_to_unreviewed_or_private_page" in result.issues


@pytest.mark.asyncio
async def test_review_failure_aborts_without_writes(dataset, pool, monkeypatch):
    shared = await scope(dataset, "shared")

    async def fail(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(privacy.llm, "complete_structured", fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await shared.tool("write_page", {"page_id": None, "title": "Lesson", "content": "Reusable"})
    assert not await pool.fetchval(
        "SELECT 1 FROM pages WHERE name='Lesson' AND owner_user_id=$1", dataset.owner
    )


@pytest.mark.asyncio
async def test_approval_with_issues_is_rejected(dataset, monkeypatch):
    shared = await scope(dataset, "shared")

    async def inconsistent(**kwargs):
        return privacy.PrivacyReview(approved=True, issues=["uncertain_identity"])

    monkeypatch.setattr(privacy.llm, "complete_structured", inconsistent)
    result = await shared.tool(
        "write_page", {"page_id": None, "title": "Lesson", "content": "Reusable"}
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_change_between_listing_and_body_read_is_blocked(dataset, pool, client, monkeypatch):
    await scope(dataset, "shared")
    original = vfs_service.ExternalVfsClient.get_overview

    def change_after_listing(self):
        result = original(self)
        asyncio.run_coroutine_threadsafe(
            pool.execute(
                "UPDATE pages SET content_markdown='PRIVATE_AFTER_LISTING' WHERE id=$1",
                dataset.shared,
            ),
            self._loop,
        ).result()
        return result

    monkeypatch.setattr(vfs_service.ExternalVfsClient, "get_overview", change_after_listing)
    response = await client.post(
        "/api/v1/me/vfs",
        json={"script": "cat /memory/Index.md"},
        headers=_auth(dataset.key),
    )
    assert response.status_code == 200, response.text
    assert "PRIVATE_AFTER_LISTING" not in response.text
    assert "unavailable" in response.text


@pytest.mark.asyncio
async def test_private_page_moved_to_shared_is_not_read_raw(dataset, pool):
    await pool.execute(
        "UPDATE pages SET folder_id=$2 WHERE id=$1",
        dataset.pages["private"],
        dataset.workspace["external_wiki_folder_id"],
    )
    assert (
        await privacy.customer_page(
            str(dataset.workspace["id"]), str(dataset.pages["private"]), "private"
        )
        is None
    )


def test_large_page_is_rejected_without_truncating_review():
    assert "page_exceeds_full_review_limit" in privacy.deterministic_issues(
        "Large", "x" * privacy.MAX_REVIEW_CHARACTERS
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("in_subfolder", [False, True])
@pytest.mark.parametrize("tagged", [False, True])
async def test_shared_folder_names_and_attachments_are_not_published(
    dataset, pool, client, in_subfolder, tagged
):
    folder = dataset.workspace["external_wiki_folder_id"]
    if in_subfolder:
        folder = await pool.fetchval(
            "INSERT INTO folders (owner_user_id,created_by,parent_folder_id,name) "
            "VALUES ($1,$1,$2,'Customer fleet dossier') RETURNING id",
            dataset.owner,
            folder,
        )
    await pool.execute("UPDATE pages SET folder_id=$2 WHERE id=$1", dataset.shared, folder)
    await scope(dataset, "shared")
    await pool.execute(
        "INSERT INTO files (owner_user_id,folder_id,name,content_type,size_bytes,storage_key,uploaded_by,end_user_id) "
        "VALUES ($1,$2,'Customer invoice.pdf','application/pdf',10,'fake-test-key',$1,$3)",
        dataset.owner,
        folder,
        dataset.users["private"]["id"] if tagged else None,
    )
    await pool.execute(
        "INSERT INTO files (owner_user_id,folder_id,name,content_type,size_bytes,storage_key,uploaded_by,end_user_id) "
        "VALUES ($1,$2,'Own attachment.pdf','application/pdf',10,'fake-private-key',$1,$3)",
        dataset.owner,
        dataset.users["private"]["wiki_folder_id"],
        dataset.users["private"]["id"],
    )
    response = await client.post(
        "/api/v1/me/vfs",
        json={"script": "find / -type f", "user_id": "private"},
        headers=_auth(dataset.key),
    )
    assert response.status_code == 200, response.text
    assert "Index.md" in response.text
    assert "dossier" not in response.text and "invoice" not in response.text
    assert "Own attachment.pdf" in response.text


@pytest.mark.asyncio
async def test_quarantined_title_collision_is_recoverable_without_exposing_body(dataset):
    shared = await curation.load_scope(
        dataset.workspace,
        "shared",
        dataset.workspace["external_wiki_folder_id"],
        [dataset.users["public"]["id"]],
        "privacy-test",
        None,
        None,
    )
    result = await shared.tool(
        "write_page", {"page_id": None, "title": "Index", "content": "New lesson"}
    )
    assert "quarantined" in result["error"]
    assert "ALLOWED_SHARED_KNOWLEDGE" not in json.dumps(result)


@pytest.mark.asyncio
async def test_shared_reads_still_enforce_document_budget(dataset, client, monkeypatch):
    await scope(dataset, "shared")
    monkeypatch.setattr(vfs_service, "MAX_DOCUMENT_READS", 0)
    response = await client.post(
        "/api/v1/me/vfs",
        json={"script": "cat /memory/Index.md"},
        headers=_auth(dataset.key),
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_customer_page_endpoint_checks_auth_scope_and_approval(dataset, client):
    path = f"/api/v1/me/vfs/pages/{dataset.shared}"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=_auth(dataset.key))).status_code == 404
    await scope(dataset, "shared")
    approved = await client.get(path, headers=_auth(dataset.key))
    assert (
        approved.status_code == 200
        and approved.json()["content_markdown"] == "ALLOWED_SHARED_KNOWLEDGE"
    )
    private_path = f"/api/v1/me/vfs/pages/{dataset.pages['private']}"
    assert (await client.get(private_path, headers=_auth(dataset.key))).status_code == 404
    assert (
        await client.get(private_path, headers=_auth(dataset.key), params={"user_id": "public"})
    ).status_code == 404
    assert (
        await client.get(private_path, headers=_auth(dataset.key), params={"user_id": "private"})
    ).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["inline", "reconciler"])
async def test_embedding_started_before_cleanup_cannot_restore_private_vector(
    dataset, pool, monkeypatch, path
):
    import hashlib

    import numpy as np

    from backend.services import embeddings, files_tree_service
    from backend.tasks.embeddings import _reconcile_pages

    await pool.execute("UPDATE pages SET embed_stale=false")
    await pool.execute(
        "UPDATE pages SET embed_stale=true,content_hash=$2 WHERE id=$1",
        dataset.shared,
        hashlib.sha256(b"ALLOWED_SHARED_KNOWLEDGE").hexdigest(),
    )

    async def racing_embed(value):
        await pool.execute(
            "UPDATE pages SET content_markdown='Sanitized lesson',content_hash=$2,"
            "embedding=NULL,embed_stale=true WHERE id=$1",
            dataset.shared,
            hashlib.sha256(b"Sanitized lesson").hexdigest(),
        )
        vector = np.zeros(384, dtype=np.float32)
        return [vector] if isinstance(value, list) else vector

    monkeypatch.setattr(embeddings, "is_configured", lambda: True)
    monkeypatch.setattr(embeddings, "embed_text", racing_embed)
    monkeypatch.setattr(embeddings, "embed_batch", racing_embed)
    if path == "inline":
        await files_tree_service._embed_page(dataset.shared, "ALLOWED_SHARED_KNOWLEDGE")
    else:
        await _reconcile_pages()
    row = await pool.fetchrow("SELECT embed_stale,embedding FROM pages WHERE id=$1", dataset.shared)
    assert row["embed_stale"] and row["embedding"] is None
