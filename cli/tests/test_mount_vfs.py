import os

from cli.mount import StashFuseOperations, StashVfsModel


class FakeClient:
    def __init__(self):
        self.page_updates = []

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
            "stashes": [
                {
                    "id": "stash-12345678",
                    "slug": "demo-stash",
                    "title": "Demo Stash",
                    "items": [],
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

    def get_stash_text(self, slug):
        assert slug == "demo-stash"
        return "# Demo Stash\n"

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
        "stashes",
        "tables",
    }
    assert model.read_file(f"{workspace_path}/stashes/Demo Stash--stash-12.md") == b"# Demo Stash\n"
    assert b"hello" in model.read_file(
        f"{workspace_path}/sessions/Fix login--session-/transcript.md"
    )
    assert b'"Name": "Mount"' in model.read_file(
        f"{workspace_path}/tables/Ideas--table-12/rows.json"
    )


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

    ops = StashFuseOperations(model)
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
