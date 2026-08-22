"""The VFS shell, served over HTTP.

The point of the endpoint is that an agent with no shell — a Vercel function, an
MCP client — gets the same filesystem the `stash vfs` CLI command gives an agent
that does. These tests pin the two properties that make that safe to hand a
partner: reads run as the calling credential, and the caller's cloud computer is
not part of the tree.
"""

import io
import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import source_service
from stashvfs.model import TRANSCRIPT_EVENTS_PAGE

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("vfs"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _vfs(client: AsyncClient, api_key: str, script: str, cwd: str = "/"):
    return await client.post(
        "/api/v1/me/vfs",
        json={"script": script, "cwd": cwd},
        headers=_auth(api_key),
    )


async def _make_page(client: AsyncClient, api_key: str, name: str, content: str) -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name, "content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _make_source_doc(owner_id: UUID, path: str, name: str, content: str) -> None:
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref=f"acme/{unique_name('repo')}",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=owner_id,
        path=path,
        name=name,
        content=content,
    )


async def test_ls_root_lists_the_mounts(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls /")

    assert resp.status_code == 200
    body = resp.json()
    assert body["exit_code"] == 0
    listed = body["stdout"].split()
    assert {"files", "sessions", "skills"} <= set(listed)
    # Tables are not a segregated section — they live inside /files (and
    # /memory) at their folder path.
    assert "tables" not in listed


async def test_tables_mount_inside_their_folder(client: AsyncClient):
    """A table about jobs belongs in the jobs folder: the VFS projects each
    table as a directory at its folder path, not under a /tables silo."""
    api_key, _ = await _register(client)
    folder = await client.post("/api/v1/me/folders", json={"name": "Jobs"}, headers=_auth(api_key))
    assert folder.status_code == 201
    table = await client.post(
        "/api/v1/me/tables",
        json={
            "name": "Applications",
            "folder_id": folder.json()["id"],
            "columns": [{"name": "Company", "type": "text"}],
        },
        headers=_auth(api_key),
    )
    assert table.status_code == 201
    row = await client.post(
        f"/api/v1/me/tables/{table.json()['id']}/rows",
        json={"data": {table.json()["columns"][0]["id"]: "Acme"}},
        headers=_auth(api_key),
    )
    assert row.status_code == 201

    listing = await _vfs(client, api_key, "ls '/files/Jobs/Applications'")
    assert listing.json()["exit_code"] == 0
    assert set(listing.json()["stdout"].split()) == {"rows.json", "rows.jsonl", "schema.json"}

    rows = await _vfs(client, api_key, "cat '/files/Jobs/Applications/rows.jsonl'")
    assert "Acme" in rows.json()["stdout"]


async def test_computer_is_not_mounted_server_side(client: AsyncClient):
    """A key handed to a partner's production agent must not reach through the
    API into a real machine's disk. /computer exists only in the CLI's mount."""
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls /")

    assert "computer" not in resp.json()["stdout"].split()


async def test_cat_reads_a_page_body(client: AsyncClient):
    """Page bodies load through a lazy loader that re-enters the app. If the
    nested request loses the caller's credential, this is where it shows up."""
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "Runbook", "# Deploy\nrun the migration first")

    resp = await _vfs(client, api_key, "cat '/files/Runbook.md'")

    assert resp.status_code == 200
    assert "run the migration first" in resp.json()["stdout"]


async def test_resolve_maps_a_vfs_path_to_its_app_route(client: AsyncClient):
    """Chat citations deep-link through /resolve: a VFS path comes back with
    the app route of the object behind it."""
    api_key, _ = await _register(client)
    page_id = await _make_page(client, api_key, "Runbook", "# Deploy")

    resp = await client.get(
        "/api/v1/me/vfs/resolve",
        params={"path": "/files/Runbook.md"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    assert resp.json() == {"path": "/files/Runbook.md", "app_url": f"/p/{page_id}"}


async def test_resolve_unknown_path_is_404(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await client.get(
        "/api/v1/me/vfs/resolve",
        params={"path": "/files/nope.md"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 404


async def test_grep_searches_connected_source_documents(client: AsyncClient):
    api_key, owner_id = await _register(client)
    await _make_source_doc(owner_id, "specs/auth.md", "auth.md", "tokens rotate hourly")

    resp = await _vfs(client, api_key, "grep -ri 'rotate hourly' /sources")

    assert resp.status_code == 200
    assert "auth.md" in resp.json()["stdout"]


async def test_reads_are_scoped_to_the_calling_credential(client: AsyncClient):
    """The whole authorization argument for this endpoint: it re-enters the app's
    own routes, so one user's key cannot see another user's page."""
    owner_key, _ = await _register(client)
    await _make_page(client, owner_key, "Secrets", "the launch date is may fourth")

    other_key, _ = await _register(client)
    resp = await _vfs(client, other_key, "grep -ri 'launch date' /files")

    assert resp.status_code == 200
    assert "may fourth" not in resp.json()["stdout"]
    assert "Secrets" not in resp.json()["stdout"]


async def test_grep_with_no_match_exits_nonzero_without_failing_the_request(
    client: AsyncClient,
):
    """A shell result, not a transport error. Callers must be able to tell the
    difference between `grep` finding nothing and the endpoint breaking."""
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "grep -ri 'nothing matches this' /files")

    assert resp.status_code == 200
    assert resp.json()["exit_code"] != 0


async def test_writes_are_rejected(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "echo hi > /files/x.md")

    assert resp.status_code == 200
    assert resp.json()["exit_code"] != 0


async def test_unknown_cwd_is_a_client_error(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls", cwd="/nope")

    assert resp.status_code == 400


async def test_scan_budget_makes_grep_partial_and_loud(client: AsyncClient, monkeypatch):
    """A scope-wide grep that outruns the read budget must return whatever it
    found so far with an explicit truncation warning — not abort with 413
    (Heavi's agent lost entire per-VIN sweeps to that), and never a clean
    no-match exit that reads as 'searched everything, found nothing'."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "One", "alpha")
    await _make_page(client, api_key, "Two", "beta")

    resp = await _vfs(client, api_key, "grep -ri 'alpha' /files")

    assert resp.status_code == 200
    body = resp.json()
    assert "of 2 files" in body["stderr"]
    assert "partial" in body["stderr"]


async def test_document_read_budget_still_aborts_direct_reads(client: AsyncClient, monkeypatch):
    """Outside a grep sweep there are no partial results to salvage: a `cat`
    over more documents than the budget allows must abort the command."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "One", "alpha")
    await _make_page(client, api_key, "Two", "beta")

    resp = await _vfs(client, api_key, "cat '/files/One.md' '/files/Two.md'")

    assert resp.status_code == 413


async def test_machine_fs_404s_without_provisioned_computer(client: AsyncClient, monkeypatch):
    """Browsing must never conjure a VM: a user who never ran a cloud agent
    gets a 404 from the machine fs, not a freshly provisioned sprite."""
    from backend.config import settings

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    api_key, _ = await _register(client)

    resp = await client.get("/api/v1/me/machine/fs", headers=_auth(api_key))

    assert resp.status_code == 404


async def test_overview_reports_machine_provisioned_state(client: AsyncClient, monkeypatch, pool):
    """The CLI VFS decides whether to mount /computer from this flag alone, so
    it must flip exactly when a ready sprite row exists — no machine API call."""
    from backend.config import settings

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    api_key, owner_id = await _register(client)

    before = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert before.json()["machine"] == {"provisioned": False}

    await pool.execute(
        "INSERT INTO user_sprites (user_id, sprite_name, status) VALUES ($1, $2, 'ready')",
        owner_id,
        "sprite-test",
    )
    after = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert after.json()["machine"] == {"provisioned": True}


async def _upload_turns(client: AsyncClient, api_key: str, session_id: str, turns: int) -> None:
    """A session of `turns` user turns, numbered so a test can name any one of
    them (msg-0 … msg-N) and know where it falls relative to the render cap."""
    body = (
        "\n".join(
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": f"msg-{i}"},
                    "timestamp": f"2026-05-10T20:00:00.{i:06d}Z",
                }
            )
            for i in range(turns)
        )
        + "\n"
    ).encode()
    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(body), "application/jsonl")},
        data={"session_id": session_id, "agent_name": "claude"},
        headers=_auth(api_key),
    )
    assert up.status_code == 201, up.text


async def _transcript_path(client: AsyncClient, api_key: str) -> str:
    """The session's transcript.md, by path. Tests must target this file
    directly: a recursive grep of the session directory also matches the
    uncapped transcript.jsonl beside it, so a `grep -r` assertion passes even
    when the markdown is completely broken. That already fooled us once."""
    located = await _vfs(client, api_key, "find /sessions -name transcript.md")
    assert located.status_code == 200
    path = located.json()["stdout"].strip()
    assert path, located.json()
    return path


async def test_short_transcript_renders_whole_and_unbannered(client: AsyncClient):
    """Under the render cap nothing is withheld, so nothing is announced. A
    banner on every session would be noise people learn to skip past."""
    api_key, _ = await _register(client)
    await _upload_turns(client, api_key, "sess-vfs-short", 150)
    path = await _transcript_path(client, api_key)

    resp = await _vfs(client, api_key, f'cat "{path}"')

    assert resp.status_code == 200
    result = resp.json()
    assert result["exit_code"] == 0, result
    assert "msg-149" in result["stdout"]
    assert "TRUNCATED" not in result["stdout"]


async def test_long_transcript_says_what_it_withheld(client: AsyncClient):
    """Over the cap the file must state that it is partial, by how much, and
    where the whole session lives — at the top for a reader who takes the first
    screenful, and at the bottom for one who reads to the end."""
    api_key, _ = await _register(client)
    turns = TRANSCRIPT_EVENTS_PAGE + 5
    await _upload_turns(client, api_key, "sess-vfs-long", turns)
    path = await _transcript_path(client, api_key)

    resp = await _vfs(client, api_key, f'cat "{path}"')

    assert resp.status_code == 200
    body = resp.json()["stdout"]
    assert body.count("TRUNCATED") == 2, "banner belongs at both ends"
    assert f"FIRST {TRANSCRIPT_EVENTS_PAGE:,} of {turns:,} events" in body
    assert f"{turns - TRANSCRIPT_EVENTS_PAGE:,} MORE events" in body
    assert "./transcript.jsonl" in body
    assert "msg-0" in body
    assert f"msg-{turns - 1}" not in body


async def test_grep_searches_the_whole_transcript_and_says_cat_will_not(
    client: AsyncClient,
):
    """The deliberate divergence, pinned in one place so it cannot be
    "tidied up" by accident: grep searches every event, while the rendered file
    stops at the cap. Complete search is worth more than a search that silently
    skips the back half of a session — but it means grep reports matches, and
    line numbers, for text that is genuinely not in the file. The stderr
    warning is what keeps that from being inexplicable.

    Changing this is a product decision, not a cleanup: update the warning and
    this test together, or not at all."""
    api_key, _ = await _register(client)
    turns = TRANSCRIPT_EVENTS_PAGE + 5
    await _upload_turns(client, api_key, "sess-vfs-grep", turns)
    path = await _transcript_path(client, api_key)
    past_the_cap = f"msg-{turns - 1}"

    found = await _vfs(client, api_key, f'grep -n "{past_the_cap}" "{path}"')

    assert found.status_code == 200
    result = found.json()
    assert result["exit_code"] == 0, result
    assert past_the_cap in result["stdout"], "grep must reach past the rendered slice"
    assert "searched in FULL" in result["stderr"]
    assert "will not find them" in result["stderr"]

    shown = await _vfs(client, api_key, f'cat "{path}"')
    assert past_the_cap not in shown.json()["stdout"], (
        "the rendered file is bounded on purpose; if this starts passing, the "
        "divergence is gone and the warning above is now a lie"
    )


async def test_events_json_reports_what_it_withheld(client: AsyncClient):
    """The machine-readable half of the same disclosure, for a caller parsing
    JSON rather than reading prose."""
    api_key, _ = await _register(client)
    turns = TRANSCRIPT_EVENTS_PAGE + 5
    await _upload_turns(client, api_key, "sess-vfs-json", turns)

    located = await _vfs(client, api_key, "find /sessions -name events.json")
    path = located.json()["stdout"].strip()
    resp = await _vfs(client, api_key, f'cat "{path}"')

    payload = json.loads(resp.json()["stdout"])
    assert payload["total"] == turns
    assert payload["shown"] == TRANSCRIPT_EVENTS_PAGE
    assert payload["truncated"] is True
    assert len(payload["events"]) == TRANSCRIPT_EVENTS_PAGE


async def test_transcript_jsonl_is_the_escape_hatch_the_banner_names(
    client: AsyncClient,
):
    """The banner sends readers to transcript.jsonl, so that file had better be
    complete. It renders from the unpaged export route and must stay that way."""
    api_key, _ = await _register(client)
    turns = TRANSCRIPT_EVENTS_PAGE + 5
    await _upload_turns(client, api_key, "sess-vfs-jsonl", turns)

    located = await _vfs(client, api_key, "find /sessions -name transcript.jsonl")
    path = located.json()["stdout"].strip()
    resp = await _vfs(client, api_key, f'cat "{path}"')

    assert f"msg-{turns - 1}" in resp.json()["stdout"]
