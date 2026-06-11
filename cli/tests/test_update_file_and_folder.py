from cli.client import StashClient


def _stub_client():
    """A StashClient with _patch stubbed to capture calls. We bypass __init__
    so we don't need real config; only _patch is exercised."""
    client = StashClient.__new__(StashClient)
    calls: list[tuple[str, dict]] = []

    def fake_patch(path: str, json=None) -> dict:
        calls.append((path, json))
        return {"id": "x", "name": (json or {}).get("name", "x")}

    client._patch = fake_patch  # type: ignore[method-assign]
    return client, calls


def test_update_ws_file_rename_only() -> None:
    c, calls = _stub_client()
    c.update_ws_file("WS", "F1", name="new.md")
    assert calls == [("/api/v1/workspaces/WS/files/F1", {"name": "new.md"})]


def test_update_ws_file_move_to_folder() -> None:
    c, calls = _stub_client()
    c.update_ws_file("WS", "F1", folder_id="FOLD")
    assert calls == [("/api/v1/workspaces/WS/files/F1", {"folder_id": "FOLD"})]


def test_update_ws_file_move_to_root_wins_over_folder_id() -> None:
    # If both are passed, move_to_root takes precedence — matches the
    # backend's elif structure (routers/files.py).
    c, calls = _stub_client()
    c.update_ws_file("WS", "F1", folder_id="FOLD", move_to_root=True)
    assert calls == [("/api/v1/workspaces/WS/files/F1", {"move_to_root": True})]


def test_update_ws_file_rename_and_move_combined() -> None:
    c, calls = _stub_client()
    c.update_ws_file("WS", "F1", name="new.md", folder_id="FOLD")
    assert calls == [("/api/v1/workspaces/WS/files/F1", {"name": "new.md", "folder_id": "FOLD"})]


def test_update_ws_file_empty_request_is_legal() -> None:
    # Backend returns the file unchanged when no fields are sent; we should
    # not silently inject any defaults.
    c, calls = _stub_client()
    c.update_ws_file("WS", "F1")
    assert calls == [("/api/v1/workspaces/WS/files/F1", {})]


def test_update_folder_rename_only() -> None:
    c, calls = _stub_client()
    c.update_folder("WS", "D1", name="Inbox 2")
    assert calls == [("/api/v1/workspaces/WS/folders/D1", {"name": "Inbox 2"})]


def test_update_folder_move_to_parent() -> None:
    c, calls = _stub_client()
    c.update_folder("WS", "D1", parent_folder_id="P1")
    assert calls == [("/api/v1/workspaces/WS/folders/D1", {"parent_folder_id": "P1"})]


def test_update_folder_move_to_root_wins_over_parent() -> None:
    c, calls = _stub_client()
    c.update_folder("WS", "D1", parent_folder_id="P1", move_to_root=True)
    assert calls == [("/api/v1/workspaces/WS/folders/D1", {"move_to_root": True})]
