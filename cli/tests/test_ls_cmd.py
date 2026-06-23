"""`stash ls` is the demo-facing answer to "what do you have access to": the
overview must show every source as a directory (integrations included), and
drilling into a path must collapse the backend's recursive prefix listing into
one directory level — otherwise the output reads as a dump, not a filesystem."""

from cli import main

SOURCES = [
    {"source": "files", "type": "native_files", "display_name": "Files", "tree": []},
    {
        "source": "sessions",
        "type": "native_sessions",
        "display_name": "Session transcripts",
        "tree": [{"name": "claude", "kind": "session", "ref": "s1"}],
    },
    {
        "source": "11111111-1111-1111-1111-111111111111",
        "type": "github_repo",
        "display_name": "stash",
        "sync_status": "idle",
        "tree": [
            {
                "name": "docs",
                "kind": "folder",
                "children": [
                    {"name": "api.md", "kind": "file", "path": "docs/api.md"},
                    {"name": "", "kind": "truncated", "hidden": 7},
                ],
            }
        ],
    },
    {
        "source": "22222222-2222-2222-2222-222222222222",
        "type": "gong_calls",
        "display_name": "Gong",
        "sync_status": "failed",
        "tree": [],
    },
]


class FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sources_tree(self, depth=3):
        return SOURCES

    def list_source_entries(self, source, path=""):
        assert source == "11111111-1111-1111-1111-111111111111"
        return [
            {"path": "docs/api.md", "name": "api.md", "kind": "file"},
            {"path": "docs/guides/intro.md", "name": "intro.md", "kind": "file"},
            {"path": "docs2/other.md", "name": "other.md", "kind": "file"},
        ]


def _setup(monkeypatch):
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: FakeClient())
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def test_ls_overview_shows_every_source_as_a_directory(monkeypatch, capsys):
    _setup(monkeypatch)

    main.ls_cmd(path="", depth=2, as_json=False)

    out = capsys.readouterr().out
    assert "files/" in out
    assert "sessions/" in out
    assert "stash/" in out
    assert "gong/" in out
    assert "api.md" in out
    assert "+7 more" in out
    assert "sync failed" in out


def test_ls_path_collapses_prefix_listing_to_one_level(monkeypatch, capsys):
    _setup(monkeypatch)

    main.ls_cmd(path="stash/docs", depth=2, as_json=False)

    out = capsys.readouterr().out
    assert "api.md" in out
    assert "guides/" in out
    # Recursive descendants and sibling prefix matches must not leak in.
    assert "intro.md" not in out
    assert "other.md" not in out


def test_ls_unknown_source_fails_loudly(monkeypatch, capsys):
    _setup(monkeypatch)

    try:
        main.ls_cmd(path="nope", depth=2, as_json=False)
    except Exception as e:
        assert type(e).__name__ == "Exit"
    out = capsys.readouterr().out
    assert "No source named 'nope'" in out
