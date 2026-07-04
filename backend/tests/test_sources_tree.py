"""The sources tree is the agent's answer to "what do you have access to"
(`stash ls`). Two properties matter beyond plain rendering:

1. EVERY visible source appears — even empty or still-syncing ones.
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


def test_build_entry_tree_leaves_display_document_name_not_path_segment():
    # Gmail-style: the path is an opaque message id; the name is the subject.
    entries = [{"path": "19eb2b5141a3bbed", "name": "Q3 board deck", "kind": "message"}]
    tree = build_entry_tree(entries, depth=3, per_dir=50)
    assert tree[0]["name"] == "Q3 board deck"
    assert tree[0]["path"] == "19eb2b5141a3bbed"


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

    async def fake_pages(owner_user_id, user_id):
        return [{"id": "p1", "name": "Welcome"}]

    async def fake_sessions(owner_user_id, user_id):
        return [
            {
                "session_id": "s1",
                "agent_name": "claude",
                "title_source": "  Fix the onboarding\nwizard  ",
            },
            {"session_id": "s2", "agent_name": "claude", "title_source": None},
        ]

    async def fake_connected(user_id):
        return [github]

    async def fake_documents(source, prefix="", limit=200):
        # The registry row itself must pass through — list_documents applies
        # the per-source security filters (Slack channel / Gong account
        # allowlists) from it.
        assert source is github
        return [{"path": "docs/api.md", "name": "api.md", "kind": "file"}]

    audits = []

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(files_tree_service, "list_scope_pages", fake_pages)
    monkeypatch.setattr(memory_service, "list_scope_sessions", fake_sessions)
    monkeypatch.setattr(source_service, "list_connected_sources", fake_connected)
    monkeypatch.setattr(source_service, "list_documents", fake_documents)
    monkeypatch.setattr(source_service, "_audit_source_read", fake_audit)

    sources = await source_service.sources_tree(uuid4(), uuid4(), depth=3)

    # Connected sources nest under their provider folder. A sole connection
    # collapses — its documents sit directly in the provider folder.
    assert [s["display_name"] for s in sources] == [
        "Files",
        "Session transcripts",
        "github",
    ]
    session_names = [n["name"] for n in sources[1]["tree"]]
    assert session_names == ["Fix the onboarding wizard", "claude"]
    assert sources[2]["type"] == "provider"
    assert sources[2]["tree"][0]["name"] == "docs"
    assert audits[0]["action"] == "source.tree_listed"


async def test_sources_tree_nests_multiple_connections_under_one_provider(monkeypatch):
    from backend.services import files_tree_service, memory_service

    repos = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "source_type": "github_repo",
            "display_name": "stash",
            "capability": "navigable",
            "sync_status": "idle",
            "last_synced_at": None,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source_type": "github_repo",
            "display_name": "plugin",
            "capability": "navigable",
            "sync_status": "idle",
            "last_synced_at": None,
        },
    ]

    async def fake_empty(owner_user_id, user_id):
        return []

    async def fake_connected(user_id):
        return repos

    async def fake_documents(source, prefix="", limit=200):
        return [{"path": "README.md", "name": "README.md", "kind": "file"}]

    async def fake_audit(**kwargs):
        pass

    monkeypatch.setattr(files_tree_service, "list_scope_pages", fake_empty)
    monkeypatch.setattr(memory_service, "list_scope_sessions", fake_empty)
    monkeypatch.setattr(source_service, "list_connected_sources", fake_connected)
    monkeypatch.setattr(source_service, "list_documents", fake_documents)
    monkeypatch.setattr(source_service, "_audit_source_read", fake_audit)

    sources = await source_service.sources_tree(uuid4(), uuid4(), depth=3)

    github = next(s for s in sources if s["display_name"] == "github")
    # Two repos → each is a subfolder under /sources/github, not a sibling of it.
    assert [n["name"] for n in github["tree"]] == ["plugin", "stash"]
    assert github["tree"][0]["source"] == "22222222-2222-2222-2222-222222222222"
    assert github["tree"][0]["children"][0]["name"] == "README.md"
    assert {m["handle"] for m in github["members"]} == {repo["id"] for repo in repos}
