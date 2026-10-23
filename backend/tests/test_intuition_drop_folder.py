"""Drop folders: files and pages added to an eval's folder become unlabeled examples, once."""

from uuid import UUID

from backend.database import get_pool
from backend.services import storage_service
from backend.services.intuition import drop_folder

from .test_intuitions import _choice_model, _register


async def test_drop_folder_imports_new_files_and_pages_once(client, monkeypatch):
    auth = await _register(client)
    model_id = await _choice_model(client, auth)

    assert (
        await client.get(f"/api/v1/intuitions/{model_id}/drop-folder", headers=auth)
    ).json() == {"folder": None}
    made = await client.post(f"/api/v1/intuitions/{model_id}/drop-folder", headers=auth)
    assert made.status_code == 201, made.text
    folder = made.json()["folder"]
    assert folder["name"] == "Replies examples"
    assert folder["url"] == f"/folders/{folder['id']}"
    again = await client.post(f"/api/v1/intuitions/{model_id}/drop-folder", headers=auth)
    assert again.json()["folder"]["id"] == folder["id"]

    pool = get_pool()
    owner = await pool.fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id = $1", UUID(model_id)
    )
    await pool.execute(
        "INSERT INTO pages (owner_user_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, 'note.md', 'please send this, thanks', $1)",
        owner,
        UUID(folder["id"]),
    )
    await pool.execute(
        "INSERT INTO pages (owner_user_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, 'empty.md', '', $1)",
        owner,
        UUID(folder["id"]),
    )
    trace = b'{"role": "user", "content": "Reply to the customer"}\n{"role": "agent", "content": "no"}\n'
    await pool.execute(
        "INSERT INTO files (owner_user_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, 'agent trace 2026-08-09.jsonl', 'application/octet-stream', $3, 'k/trace', $1)",
        owner,
        UUID(folder["id"]),
        len(trace),
    )

    async def download(key):
        assert key == "k/trace"
        return trace

    monkeypatch.setattr(storage_service, "download_file", download)
    assert UUID(model_id) in await drop_folder.due()

    synced = await client.post(f"/api/v1/intuitions/{model_id}/drop-folder/sync", headers=auth)
    assert synced.json() == {"added": 2, "failed": 1}
    assert await drop_folder.sync(UUID(model_id)) == {"added": 0, "failed": 0}
    assert UUID(model_id) not in await drop_folder.due()

    examples = (await client.get(f"/api/v1/intuitions/{model_id}/examples", headers=auth)).json()
    dropped = [e for e in examples if e["note"].startswith("From the drop folder")]
    assert sorted(e["item"]["name"] for e in dropped) == ["agent trace 2026-08-09.jsonl", "note.md"]
    assert all(e["needs_review"] and e["label"] is None for e in dropped)
    trace_item = next(e["item"] for e in dropped if e["item"]["name"].endswith(".jsonl"))
    assert "Reply to the customer" in trace_item["content"]

    shown = await client.get(f"/api/v1/intuitions/{model_id}/drop-folder", headers=auth)
    assert shown.json()["folder"]["imported"] == 2


async def test_drop_folder_routes_are_owner_only(client):
    owner = await _register(client)
    other = await _register(client)
    model_id = await _choice_model(client, owner)
    for method, path in (
        ("GET", "/drop-folder"),
        ("POST", "/drop-folder"),
        ("POST", "/drop-folder/sync"),
    ):
        resp = await client.request(method, f"/api/v1/intuitions/{model_id}{path}", headers=other)
        assert resp.status_code == 404, (method, path, resp.text)
