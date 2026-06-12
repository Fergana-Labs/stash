"""The sources tree is the agent's answer to "what do you have access to"
(`stash ls`). Two properties matter beyond plain rendering:

1. EVERY visible source appears — even empty, still-syncing, or queryable ones.
   A missing source reads as "Stash can't see it", which is the exact
   impression the feature exists to kill.
2. Truncation is marked, never silent. A capped directory must say how much it
   hid, or the tree lies about the company's footprint.
"""

from uuid import uuid4

from backend.services import source_service
from backend.services.source_service import build_entry_tree


def test_build_entry_tree_nests_paths_into_folders():
    entries = [
        {"path": "docs/api.md", "name": "api.md", "kind": "file"},
        {"path": "docs/guide.md", "name": "guide.md", "kind": "file"},
        {"path": "README.md", "name": "README.md", "kind": "file"},
    ]
    tree = build_entry_tree(entries, depth=3, per_dir=50)
    assert [n["name"] for n in tree] == ["README.md", "docs"]
    docs = tree[1]
    assert docs["kind"] == "folder"
    assert [n["name"] for n in docs["children"]] == ["api.md", "guide.md"]


def test_build_entry_tree_keeps_entry_kind_and_path_on_leaves():
    entries = [{"path": "#eng/2026-06-01/1717.ts", "name": "1717.ts", "kind": "message"}]
    tree = build_entry_tree(entries, depth=3, per_dir=50)
    leaf = tree[0]["children"][0]["children"][0]
    assert leaf["kind"] == "message"
    assert leaf["path"] == "#eng/2026-06-01/1717.ts"


def test_build_entry_tree_trims_to_depth():
    entries = [{"path": "a/b/c/d.md", "name": "d.md", "kind": "file"}]
    tree = build_entry_tree(entries, depth=2, per_dir=50)
    b = tree[0]["children"][0]
    assert b["name"] == "b"
    assert "children" not in b


def test_build_entry_tree_marks_truncation_instead_of_silently_dropping():
    entries = [{"path": f"f{i}.md", "name": f"f{i}.md", "kind": "file"} for i in range(5)]
    tree = build_entry_tree(entries, depth=1, per_dir=3)
    assert len(tree) == 4
    assert tree[-1] == {"name": "", "kind": "truncated", "hidden": 2}


async def test_sources_tree_includes_every_visible_source(monkeypatch):
    from backend.services import files_tree_service, memory_service

    github = {
        "id": "11111111-1111-1111-1111-111111111111",
        "source_type": "github_repo",
        "display_name": "stash",
        "capability": "navigable",
        "sync_status": "idle",
        "last_synced_at": None,
    }
    snowflake = {
        "id": "22222222-2222-2222-2222-222222222222",
        "source_type": "snowflake",
        "display_name": "warehouse",
        "capability": "queryable",
        "sync_status": "idle",
        "last_synced_at": None,
    }

    async def fake_pages(workspace_id, user_id):
        return [{"id": "p1", "name": "Welcome"}]

    async def fake_sessions(workspace_id, user_id):
        return [{"session_id": "s1", "agent_name": "claude"}]

    async def fake_connected(workspace_id, user_id):
        return [github, snowflake]

    async def fake_documents(source, prefix="", limit=200):
        # The registry row itself must pass through — list_documents applies
        # the per-source security filters (Slack channel / Gong workspace
        # allowlists) from it.
        assert source is github
        return [{"path": "docs/api.md", "name": "api.md", "kind": "file"}]

    audits = []

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(files_tree_service, "list_workspace_pages", fake_pages)
    monkeypatch.setattr(memory_service, "list_workspace_sessions", fake_sessions)
    monkeypatch.setattr(source_service, "list_connected_sources", fake_connected)
    monkeypatch.setattr(source_service, "list_documents", fake_documents)
    monkeypatch.setattr(source_service, "_audit_source_read", fake_audit)

    sources = await source_service.sources_tree(uuid4(), uuid4(), depth=3)

    assert [s["display_name"] for s in sources] == [
        "Files",
        "Session transcripts",
        "stash",
        "warehouse",
    ]
    assert sources[2]["tree"][0]["name"] == "docs"
    assert sources[3]["tree"] == []
    assert audits[0]["action"] == "source.tree_listed"
