"""The cartridge/sharing CLI commands are thin wrappers over client methods.
These lock in the wiring: the right client call with the right arguments, so
the per-person sharing model, cartridge members/invites, session folders, and
source snapshots all reach the server correctly."""

from cli import main


class _FakeClient:
    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    # object sharing
    def share_object(self, object_type, object_id, email, permission="read", expires_at=None):
        self._calls.append(("share", object_type, object_id, email, permission))
        return {"pending": True, "email": email}

    def unshare_object(self, object_type, object_id, principal_type, principal_id):
        self._calls.append(("unshare", object_type, object_id, principal_type, principal_id))

    def list_object_shares(self, object_type, object_id):
        self._calls.append(("list_shares", object_type, object_id))
        return [{"display_name": "Sam", "permission": "read", "principal_id": "u1"}]

    # cartridge invites + snapshot (cartridge access goes through the
    # generic shares commands with object_type="stash")
    def list_cartridge_invites(self):
        self._calls.append(("invites",))
        return [
            {
                "cartridge_title": "Specs",
                "invited_by_display_name": "Sam",
                "permission": "read",
                "id": "inv1",
            }
        ]

    def snapshot_source_into_cartridge(self, workspace_id, cartridge_id, source_id, path):
        self._calls.append(("snapshot", workspace_id, cartridge_id, source_id, path))
        return {"id": "page-1"}

    # session folders
    def list_session_folders(self, workspace_id):
        self._calls.append(("folders", workspace_id))
        return [{"name": "Launch", "id": "f1"}]

    def create_session_folder(self, workspace_id, name):
        self._calls.append(("new_folder", workspace_id, name))
        return {"id": "f1", "name": name}

    def assign_session_folder(self, workspace_id, session_row_id, folder_id=None):
        self._calls.append(("assign", workspace_id, session_row_id, folder_id))
        return {"ok": True}


def _wire(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "ws-1")
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(calls))
    return calls


def test_shares_add_and_remove(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.shares_add("folder", "fold-1", "a@b.com", permission="write", as_json=True)
    main.shares_rm("folder", "fold-1", "u9", principal_type="user")
    assert ("share", "folder", "fold-1", "a@b.com", "write") in calls
    assert ("unshare", "folder", "fold-1", "user", "u9") in calls


def test_cartridge_shares_invites_and_snapshot(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.shares_add("stash", "cart-1", "sam@example.com", permission="write", as_json=True)
    main.shares_ls("stash", "cart-1", as_json=True)
    main.stashes_invites(as_json=True)
    main.stashes_snapshot_source(
        "cart-1", source="src-1", path="specs/auth.md", workspace_id=None, as_json=True
    )
    assert ("share", "stash", "cart-1", "sam@example.com", "write") in calls
    assert ("list_shares", "stash", "cart-1") in calls
    assert ("invites",) in calls
    assert ("snapshot", "ws-1", "cart-1", "src-1", "specs/auth.md") in calls


def test_session_folders(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.hist_folders(workspace_id=None, as_json=True)
    main.hist_new_folder("Launch", workspace_id=None, as_json=True)
    main.hist_assign("sess-1", folder="f1", workspace_id=None)
    assert ("folders", "ws-1") in calls
    assert ("new_folder", "ws-1", "Launch") in calls
    assert ("assign", "ws-1", "sess-1", "f1") in calls
