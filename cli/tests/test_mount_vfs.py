import os
from pathlib import Path

from cli.mount import (
    MountError,
    SkillFuseOperations,
    StashVfsModel,
    _require_macos_fskit_mountpoint,
)


class FakeClient:
    def __init__(self):
        self.page_updates = []
        self.source_entry_calls = 0

    def list_workspaces(self):
        return [{"id": "workspace-12345678", "name": "Demo Workspace", "description": "Demo"}]

    def get_workspace_overview(self, workspace_id):
        assert workspace_id == "workspace-12345678"
        return {
            "files": {
                "folders": [{"id": "folder-12345678", "name": "Notes", "parent_folder_id": None}],
                "pages": [
                    {
                        "id": "page-12345678",
                        "name": "Plan",
                        "content_type": "markdown",
                        "folder_id": "folder-12345678",
                    }
                ],
                "files": [
                    {
                        "id": "file-12345678",
                        "name": "diagram.txt",
                        "folder_id": None,
                        "size_bytes": 12,
                    }
                ],
            },
            "skills": [
                {
                    "folder_id": "skillfolder-12345678",
                    "name": "Demo Skill",
                    "file_count": 1,
                    "published": {"slug": "demo-stash"},
                }
            ],
            "sessions": [
                {
                    "id": "session-row-12345678",
                    "session_id": "session-abc",
                    "title": "Fix login",
                    "agent_name": "codex",
                }
            ],
        }

    def get_page(self, workspace_id, page_id):
        assert workspace_id == "workspace-12345678"
        assert page_id == "page-12345678"
        return {"content_type": "markdown", "content_markdown": "# Plan\n", "content_html": ""}

    def update_page(self, workspace_id, page_id, **kwargs):
        self.page_updates.append((workspace_id, page_id, kwargs))
        return {}

    def download_ws_file(self, workspace_id, file_id):
        assert workspace_id == "workspace-12345678"
        assert file_id == "file-12345678"
        return b"diagram body"

    def get_skill_text(self, slug):
        assert slug == "demo-stash"
        return "# Demo Stash\n"

    def list_sources(self, workspace_id):
        assert workspace_id == "workspace-12345678"
        return [
            {"type": "native_files", "source": "files", "display_name": "Files"},
            {"type": "gmail", "source": "src-gmail-1", "display_name": "Gmail (demo@x.com)"},
        ]

    def list_source_entries(self, workspace_id, source, path=""):
        assert workspace_id == "workspace-12345678"
        assert source == "src-gmail-1"
        self.source_entry_calls += 1
        return [
            {"path": "msg-1", "name": "Welcome email", "kind": "message"},
            {"path": "threads/msg-2", "name": "Nested note", "kind": "message"},
        ]

    def read_source_doc(self, workspace_id, source, ref):
        assert workspace_id == "workspace-12345678"
        assert source == "src-gmail-1"
        return {"content": f"BODY of {ref}"}

    def get_transcript_events(self, workspace_id, session_id):
        assert workspace_id == "workspace-12345678"
        assert session_id == "session-abc"
        return [{"role": "user", "content": "hello", "created_at": "2026-05-19T10:00:00Z"}]

    def export_transcript_jsonl(self, workspace_id, session_id):
        assert workspace_id == "workspace-12345678"
        assert session_id == "session-abc"
        return '{"type":"user"}\n'

    def list_tables(self, workspace_id):
        assert workspace_id == "workspace-12345678"
        return [{"id": "table-12345678", "name": "Ideas", "columns": [], "row_count": 1}]

    def get_table(self, workspace_id, table_id):
        assert workspace_id == "workspace-12345678"
        assert table_id == "table-12345678"
        return {"id": table_id, "name": "Ideas", "columns": []}

    def list_table_rows(
        self,
        workspace_id,
        table_id,
        limit=1000,
        offset=0,
        sort_by="",
        sort_order="asc",
        filters="",
    ):
        assert workspace_id == "workspace-12345678"
        assert table_id == "table-12345678"
        assert limit == 1000
        assert offset == 0
        return {
            "rows": [{"id": "row-1", "data": {"Name": "Mount"}}],
            "total_count": 1,
            "has_more": False,
        }


def _model():
    model = StashVfsModel(FakeClient())
    model.refresh()
    return model


def test_vfs_exposes_workspace_sections():
    model = _model()
    workspace_name = model.list_dir("/workspaces")[0]
    workspace_path = f"/workspaces/{workspace_name}"

    assert set(model.list_dir(workspace_path)) == {
        "README.md",
        "files",
        "sessions",
        "skills",
        "tables",
        "sources",
    }
    assert model.read_file(f"{workspace_path}/skills/Demo Skill--skillfol.md") == b"# Demo Stash\n"
    assert b"hello" in model.read_file(
        f"{workspace_path}/sessions/Fix login--session-/transcript.md"
    )
    assert b'"Name": "Mount"' in model.read_file(
        f"{workspace_path}/tables/Ideas--table-12/rows.json"
    )

    # Connected sources are mounted read-only; native sources are skipped
    # (files/sessions already appear above). Document bodies load lazily.
    assert model.list_dir(f"{workspace_path}/sources") == ["gmail-demo-x.com"]
    gmail = f"{workspace_path}/sources/gmail-demo-x.com"
    assert "Welcome email" in model.list_dir(gmail)
    assert model.read_file(f"{gmail}/Welcome email") == b"BODY of msg-1"
    assert model.read_file(f"{gmail}/threads/Nested note") == b"BODY of threads/msg-2"


def test_vfs_loads_source_entries_lazily():
    # Listing source names must not fetch any source's contents — that's the
    # whole point: enumerating a 10k-doc source costs the same as a 1-doc one.
    client = FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    workspace_name = model.list_dir("/workspaces")[0]
    sources_path = f"/workspaces/{workspace_name}/sources"

    assert model.list_dir(sources_path) == ["gmail-demo-x.com"]
    assert client.source_entry_calls == 0

    # Descending into a source materializes only that source, once.
    model.list_dir(f"{sources_path}/gmail-demo-x.com")
    assert client.source_entry_calls == 1
    model.list_dir(f"{sources_path}/gmail-demo-x.com")
    assert client.source_entry_calls == 1


def test_vfs_reads_files_and_writes_pages():
    client = FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    workspace_name = model.list_dir("/workspaces")[0]
    files_path = f"/workspaces/{workspace_name}/files"
    upload_name = next(name for name in model.list_dir(files_path) if name.startswith("diagram--"))

    assert model.read_file(f"{files_path}/{upload_name}") == b"diagram body"

    folder_name = next(name for name in model.list_dir(files_path) if name.startswith("Notes--"))
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(name for name in model.list_dir(folder_path) if name.startswith("Plan--"))
    page_path = f"{folder_path}/{page_name}"
    assert model.read_file(page_path) == b"# Plan\n"
    model.write_file(page_path, b"# Updated\n")

    assert client.page_updates == [
        (
            "workspace-12345678",
            "page-12345678",
            {"content": "# Updated\n"},
        )
    ]


def test_fuse_operations_commit_page_writes_on_flush():
    client = FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    workspace_name = model.list_dir("/workspaces")[0]
    files_path = f"/workspaces/{workspace_name}/files"
    folder_name = next(name for name in model.list_dir(files_path) if name.startswith("Notes--"))
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(name for name in model.list_dir(folder_path) if name.startswith("Plan--"))
    page_path = f"{folder_path}/{page_name}"

    ops = SkillFuseOperations(model)
    handle = ops.open(page_path, os.O_RDWR | os.O_TRUNC)
    ops.write(page_path, b"# Edited through FUSE\n", 0, handle)
    ops.flush(page_path, handle)
    ops.release(page_path, handle)

    assert client.page_updates == [
        (
            "workspace-12345678",
            "page-12345678",
            {"content": "# Edited through FUSE\n"},
        )
    ]


def test_fuse_operations_support_fusepy_dispatch():
    model = _model()
    workspace_name = model.list_dir("/workspaces")[0]
    workspace_path = f"/workspaces/{workspace_name}"
    ops = SkillFuseOperations(model)

    assert ops("getattr", "/")["st_nlink"] == 2
    assert "files" in [entry[0] for entry in ops("readdir", workspace_path, None)]
    dir_handle = ops("opendir", workspace_path)
    assert dir_handle > 0
    assert ops("releasedir", workspace_path, dir_handle) == 0
    assert ops("access", f"{workspace_path}/README.md", os.R_OK) == 0
    assert ops("listxattr", workspace_path) == []
    assert ops("statfs", workspace_path)["f_bsize"] == 4096


def test_macos_fskit_mountpoints_must_live_under_volumes():
    _require_macos_fskit_mountpoint(Path("/Volumes/Stash"))

    try:
        _require_macos_fskit_mountpoint(Path("~/SkillMount"))
    except MountError as e:
        assert "/Volumes/Stash" in str(e)
    else:
        raise AssertionError("expected a mountpoint error")
