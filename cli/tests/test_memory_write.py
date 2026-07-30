"""`stash memory write` resolves a path under the Memory folder to a page
slot: existing pages are found by name (so the command updates instead of
duplicating), and missing intermediate folders are created on the way down.
"""

from __future__ import annotations

import pytest

from cli.main import _resolve_memory_target

MEMORY_FOLDER = {"id": "mem-root"}


class _FakeClient:
    def __init__(self, tree: dict):
        self._tree = tree
        self.created_folders: list[tuple[str, str]] = []

    def get_memory_folder(self) -> dict:
        return MEMORY_FOLDER

    def get_memory_tree(self) -> dict:
        return self._tree

    def create_folder(self, name: str, parent_folder_id: str | None = None) -> dict:
        self.created_folders.append((name, parent_folder_id))
        return {"id": f"new-{name}"}


def _tree(folders: list | None = None, pages: list | None = None) -> dict:
    return {"folders": folders or [], "pages": pages or []}


def test_existing_root_page_is_found():
    client = _FakeClient(_tree(pages=[{"id": "p1", "name": "Log"}]))
    page, folder_id, name = _resolve_memory_target(client, "Log")
    assert page["id"] == "p1"
    assert folder_id == "mem-root"
    assert name == "Log"
    assert client.created_folders == []


def test_md_suffix_matches_the_vfs_rendering():
    """The VFS shows pages as `<name>.md`, so agents naturally pass that back."""
    client = _FakeClient(_tree(pages=[{"id": "p1", "name": "Log"}]))
    page, _, name = _resolve_memory_target(client, "Log.md")
    assert page["id"] == "p1"
    assert name == "Log"


def test_new_page_in_existing_category():
    category = _tree(pages=[{"id": "p2", "name": "Other"}]) | {"id": "f1", "name": "Product"}
    client = _FakeClient(_tree(folders=[category]))
    page, folder_id, name = _resolve_memory_target(client, "Product/Chainbase")
    assert page is None
    assert folder_id == "f1"
    assert name == "Chainbase"
    assert client.created_folders == []


def test_missing_folders_are_created_down_the_path():
    client = _FakeClient(_tree())
    page, folder_id, name = _resolve_memory_target(client, "Customers/Chainbase/Notes")
    assert page is None
    assert client.created_folders == [("Customers", "mem-root"), ("Chainbase", "new-Customers")]
    assert folder_id == "new-Chainbase"
    assert name == "Notes"


def test_pathless_input_is_rejected():
    client = _FakeClient(_tree())
    with pytest.raises(ValueError):
        _resolve_memory_target(client, "/")
