"""Command-level tests for the session-folder CLI surface.

`stash sessions folders / new-folder / rename-folder / delete-folder /
assign` are thin wrappers over the /api/v1/me/session-folders endpoints. A
fake client records every call so each command's wiring — which endpoint it
hits, in what order, with what args — is locked; StashError paths assert the
loud-failure contract (exit 1, server detail surfaced).
"""

from __future__ import annotations

import json
from unittest import mock

from typer.testing import CliRunner

from cli.client import StashError
from cli.main import app

runner = CliRunner()

DEFAULT_ROW = {
    "id": "folder-default",
    "slug": "default",
    "name": "Default",
    "access": "private",
    "public_permission": "none",
    "discoverable": False,
    "is_default": True,
    "session_count": 3,
}
PUBLIC_ROW = {
    "id": "folder-public",
    "slug": "launch-notes",
    "name": "Launch Notes",
    "access": "public",
    "public_permission": "read",
    "discoverable": True,
    "is_default": False,
    "session_count": 5,
}


class FakeClient:
    """Records every call and serves a fixed folder listing: one Default
    folder plus one public discoverable folder. resolve_session maps known
    titles to row ids and echoes anything else — the same pass-through the
    server applies to row ids."""

    TITLES = {"Debugging auth": "row-42"}

    def __init__(self, folders=None):
        self.calls: list[tuple] = []
        self.fail: dict[str, StashError] = {}
        self.folders = list(folders) if folders is not None else [DEFAULT_ROW, PUBLIC_ROW]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _fail_if(self, method: str) -> None:
        if method in self.fail:
            raise self.fail[method]

    def list_session_folders(self):
        self.calls.append(("list",))
        self._fail_if("list")
        return {"folders": [dict(f) for f in self.folders]}

    def create_session_folder(self, name, public=False, discoverable=False):
        self.calls.append(("create", name, public, discoverable))
        self._fail_if("create")
        return {"id": "folder-new", "slug": "launch-notes-x7k2p9", "name": name}

    def update_session_folder(self, folder_id, name=None):
        self.calls.append(("update", folder_id, name))
        self._fail_if("update")
        row = next(f for f in self.folders if f["id"] == folder_id)
        return {**row, "name": name}

    def delete_session_folder(self, folder_id):
        self.calls.append(("delete", folder_id))
        self._fail_if("delete")

    def assign_sessions(self, session_row_ids, folder_id):
        self.calls.append(("assign", list(session_row_ids), folder_id))
        self._fail_if("assign")
        return {"ok": True, "moved": len(session_row_ids)}

    def resolve_session(self, ref, trashed=False):
        self.calls.append(("resolve", ref))
        self._fail_if("resolve")
        return {"id": self.TITLES.get(ref, ref), "session_id": f"sid-{ref}", "matched": True}


def _run(args: list[str], fake: FakeClient):
    with mock.patch("cli.main._client", return_value=fake):
        return runner.invoke(app, ["sessions", *args])


def _kinds(fake: FakeClient) -> list[str]:
    return [call[0] for call in fake.calls]


def test_folders_lists_names_slugs_counts_and_markers() -> None:
    fake = FakeClient()
    result = _run(["folders"], fake)
    assert result.exit_code == 0
    assert "Default" in result.output
    assert "launch-notes" in result.output
    assert "5 sessions" in result.output
    assert "default" in result.output
    assert "public" in result.output
    assert "discoverable" in result.output
    assert _kinds(fake) == ["list"]


def test_folders_json_prints_api_envelope() -> None:
    fake = FakeClient()
    result = _run(["folders", "--json"], fake)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert {f["id"] for f in data["folders"]} == {"folder-default", "folder-public"}


def test_folders_empty_listing_prints_hint() -> None:
    fake = FakeClient(folders=[])
    result = _run(["folders"], fake)
    assert result.exit_code == 0
    assert "No session folders" in result.output


def test_new_folder_defaults_to_private() -> None:
    fake = FakeClient()
    result = _run(["new-folder", "Launch Notes"], fake)
    assert result.exit_code == 0
    assert fake.calls == [("create", "Launch Notes", False, False)]
    assert "folder-new" in result.output
    assert "launch-notes-x7k2p9" in result.output


def test_new_folder_public_discoverable() -> None:
    fake = FakeClient()
    result = _run(["new-folder", "Public Stuff", "--public", "--discoverable"], fake)
    assert result.exit_code == 0
    assert fake.calls == [("create", "Public Stuff", True, True)]


def test_new_folder_discoverable_requires_public() -> None:
    fake = FakeClient()
    result = _run(["new-folder", "X", "--discoverable"], fake)
    assert result.exit_code == 1
    assert "--discoverable requires --public" in result.output
    assert fake.calls == []


def test_new_folder_surfaces_server_error() -> None:
    fake = FakeClient()
    fake.fail["create"] = StashError(422, "Discoverable folders must be public")
    result = _run(["new-folder", "X"], fake)
    assert result.exit_code == 1
    assert "Discoverable folders must be public" in result.output


def test_rename_folder_by_slug_resolves_then_updates() -> None:
    fake = FakeClient()
    result = _run(["rename-folder", "launch-notes", "--name", "Launch v2"], fake)
    assert result.exit_code == 0
    assert fake.calls == [("list",), ("update", "folder-public", "Launch v2")]
    assert "Launch v2" in result.output
    assert "folder-public" in result.output


def test_rename_folder_by_id_uses_same_path() -> None:
    fake = FakeClient()
    result = _run(["rename-folder", "folder-public", "--name", "Launch v2"], fake)
    assert result.exit_code == 0
    assert fake.calls == [("list",), ("update", "folder-public", "Launch v2")]


def test_rename_folder_unknown_ref_fails_loud() -> None:
    fake = FakeClient()
    result = _run(["rename-folder", "nope", "--name", "X"], fake)
    assert result.exit_code == 1
    assert "No session folder 'nope'" in result.output
    assert "update" not in _kinds(fake)


def test_delete_folder_by_slug_deletes_resolved_id() -> None:
    fake = FakeClient()
    result = _run(["delete-folder", "launch-notes"], fake)
    assert result.exit_code == 0
    assert fake.calls == [("list",), ("delete", "folder-public")]
    assert "unfiled" in result.output


def test_assign_title_to_folder_resolves_both_ends() -> None:
    fake = FakeClient()
    result = _run(["assign", "Debugging auth", "--folder", "launch-notes"], fake)
    assert result.exit_code == 0
    assert ("resolve", "Debugging auth") in fake.calls
    assert ("assign", ["row-42"], "folder-public") in fake.calls
    assert "1 session(s) filed into 'Launch Notes'" in result.output


def test_assign_row_id_unassign_clears_folder() -> None:
    fake = FakeClient()
    result = _run(["assign", "row-7", "--unassign"], fake)
    assert result.exit_code == 0
    assert ("assign", ["row-7"], None) in fake.calls
    assert "unfiled" in result.output


def test_assign_requires_folder_or_unassign() -> None:
    fake = FakeClient()
    result = _run(["assign", "row-7"], fake)
    assert result.exit_code == 1
    assert "Pass exactly one of --folder" in result.output
    assert "assign" not in _kinds(fake)


def test_assign_refuses_folder_and_unassign_together() -> None:
    fake = FakeClient()
    result = _run(["assign", "row-7", "--folder", "launch-notes", "--unassign"], fake)
    assert result.exit_code == 1
    assert "Pass exactly one of --folder" in result.output
    assert "assign" not in _kinds(fake)


def test_assign_unknown_folder_fails_loud() -> None:
    fake = FakeClient()
    result = _run(["assign", "row-7", "--folder", "nope"], fake)
    assert result.exit_code == 1
    assert "No session folder 'nope'" in result.output
    assert "assign" not in _kinds(fake)


def test_assign_surfaces_server_error() -> None:
    fake = FakeClient()
    fake.fail["assign"] = StashError(404, "Session or folder not found")
    result = _run(["assign", "row-7", "--folder", "launch-notes"], fake)
    assert result.exit_code == 1
    assert "Session or folder not found" in result.output
