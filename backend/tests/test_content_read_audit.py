"""Native content reads land in security_audit_events.

Connected-source reads were already audited (source.document_read); these
tests pin the new content.* trail: every native document read and listing
writes exactly one row with the actor, the owning scope, and the target —
the raw feed for the usage-analytics page.
"""

import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import source_service

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("readaudit"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_page(client: AsyncClient, api_key: str, name: str, content: str) -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name, "content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _metadata(row) -> dict:
    # record_event json.dumps() into a jsonb column whose codec encodes again,
    # so raw fetches see a JSON string — same decode the service's reader does.
    metadata = row["metadata"]
    return json.loads(metadata) if isinstance(metadata, str) else metadata


async def _read_events(pool, action: str) -> list:
    return await pool.fetch(
        "SELECT * FROM security_audit_events WHERE action = $1 ORDER BY created_at",
        action,
    )


async def test_page_read_is_logged(client: AsyncClient, pool):
    api_key, user_id = await _register(client)
    page_id = await _make_page(client, api_key, "Notes.md", "hello")

    resp = await client.get(f"/api/v1/me/pages/{page_id}", headers=_auth(api_key))
    assert resp.status_code == 200

    rows = await _read_events(pool, "content.page_read")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == user_id
    assert rows[0]["owner_user_id"] == user_id
    assert rows[0]["target_type"] == "page"
    assert rows[0]["target_id"] == page_id
    assert rows[0]["via"] == "cli"


async def test_public_page_read_logs_anonymous_actor(client: AsyncClient, pool):
    api_key, user_id = await _register(client)
    page_id = await _make_page(client, api_key, "Public.md", "shared with the world")
    resp = await client.patch(
        "/api/v1/share/general-access",
        json={"object_type": "page", "object_id": page_id, "public_permission": "read"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 200

    rows = await _read_events(pool, "content.page_read")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] is None
    assert rows[0]["owner_user_id"] == user_id
    assert rows[0]["target_id"] == page_id
    assert rows[0]["via"] == "web"


async def test_source_front_door_page_read_logs_exactly_once(client: AsyncClient, pool):
    """A native page read via /sources/files/doc must produce one
    source.document_read row and no content.page_read row — the front door
    calls the service layer directly, so the page route never fires."""
    api_key, _ = await _register(client)
    page_id = await _make_page(client, api_key, "ViaSource.md", "front door")

    resp = await client.get(
        f"/api/v1/me/sources/{source_service.NATIVE_FILES}/doc",
        params={"ref": page_id},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    assert len(await _read_events(pool, "source.document_read")) == 1
    assert len(await _read_events(pool, "content.page_read")) == 0


async def test_vfs_cat_logs_page_read(client: AsyncClient, pool):
    """The server-side VFS re-enters the REST routes over nested ASGI, so an
    ask-the-stash `cat` shows up in the read trail like any other caller."""
    api_key, user_id = await _register(client)
    await _make_page(client, api_key, "Runbook.md", "step one")

    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "cat '/files/Runbook.md'", "cwd": "/"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["exit_code"] == 0

    rows = await _read_events(pool, "content.page_read")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == user_id
    assert rows[0]["via"] == "ask"


async def test_vfs_mount_listings_are_tagged_auto_not_ask(client: AsyncClient, pool):
    """Every VFS command rebuilds the tree, firing the overview/memory-folder/
    tables listing routes. Those rows must carry via='auto' (excluded from
    content-activity analytics, like the skills sync) — otherwise one `cat`
    shows up as several listings the user never asked for. The read itself
    keeps its real surface tag."""
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "Runbook.md", "step one")

    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "cat '/files/Runbook.md'", "cwd": "/"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["exit_code"] == 0

    listings = await _read_events(pool, "content.entries_listed")
    assert {r["target_type"] for r in listings} == {"overview", "memory_folder", "tables"}
    assert all(r["via"] == "auto" for r in listings)
    reads = await _read_events(pool, "content.page_read")
    assert [r["via"] for r in reads] == ["ask"]


async def test_vfs_grep_counts_as_one_search_not_many_reads(client: AsyncClient, pool):
    """A recursive grep reads every document it walks — one agent search used
    to land in analytics as hundreds of user-driven 'ask' reads. The sweep's
    reads must carry via='scan' (kept for the security trail, excluded from
    analytics) and the grep itself one source.searched row on the caller's
    real surface."""
    api_key, user_id = await _register(client)
    await _make_page(client, api_key, "One.md", "alpha needle")
    await _make_page(client, api_key, "Two.md", "beta")
    await _make_page(client, api_key, "Three.md", "gamma needle")

    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "grep -r 'needle' /files", "cwd": "/"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["exit_code"] == 0

    reads = await _read_events(pool, "content.page_read")
    assert len(reads) == 3
    assert all(r["via"] == "scan" for r in reads)

    searches = await _read_events(pool, "source.searched")
    assert len(searches) == 1
    assert searches[0]["actor_user_id"] == user_id
    assert searches[0]["target_type"] == "vfs"
    assert searches[0]["target_id"] == "/files"
    # The nested search POST arrives via the server-side VFS's client, so it
    # carries the ask surface — a `stash vfs` grep records the same row as cli.
    assert searches[0]["via"] == "ask"
    assert _metadata(searches[0])["docs_scanned"] == 3


async def test_tree_listing_is_logged(client: AsyncClient, pool):
    api_key, user_id = await _register(client)
    await _make_page(client, api_key, "One.md", "x")

    resp = await client.get("/api/v1/me/tree", headers=_auth(api_key))
    assert resp.status_code == 200

    rows = await _read_events(pool, "content.entries_listed")
    tree_rows = [r for r in rows if r["target_type"] == "tree"]
    assert len(tree_rows) == 1
    assert tree_rows[0]["actor_user_id"] == user_id
    assert _metadata(tree_rows[0])["result_count"] >= 1


async def test_transcript_export_is_logged(client: AsyncClient, pool):
    api_key, user_id = await _register(client)
    session_id = "read-audit-session"
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "session_id": session_id,
            "agent_name": "tester",
            "event_type": "user_message",
            "content": "hi",
            "created_at": "2026-01-02T00:00:00Z",
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(
        f"/api/v1/me/transcripts/{session_id}/export.jsonl",
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    rows = await _read_events(pool, "content.transcript_read")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == user_id
    assert rows[0]["target_id"] == session_id
    assert _metadata(rows[0]) == {"kind": "export"}


async def test_auto_marked_read_is_audited_with_via_auto(client: AsyncClient, pool):
    """Automated machinery (skills sync, plugin hooks) sends X-Stash-Via: auto.
    The read is still audited, but tagged so content-activity analytics can
    exclude it — only reads someone asked for count as document reads."""
    api_key, user_id = await _register(client)
    page_id = await _make_page(client, api_key, "Auto.md", "hello")

    resp = await client.get(
        f"/api/v1/me/pages/{page_id}",
        headers={**_auth(api_key), "X-Stash-Via": "auto"},
    )
    assert resp.status_code == 200

    rows = await _read_events(pool, "content.page_read")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == user_id
    assert rows[0]["via"] == "auto"
