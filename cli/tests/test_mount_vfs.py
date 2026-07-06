from cli.mount import StashVfsModel


class FakeClient:
    def __init__(self):
        self.source_entry_calls = 0

    def get_overview(self):
        return {
            "files": {
                "folders": [{"id": "folder-12345678", "name": "Notes", "parent_folder_id": None}],
                "pages": [
                    {
                        "id": "page-12345678",
                        "name": "Plan",
                        "content_type": "markdown",
                        "folder_id": "folder-12345678",
                        "created_at": "2026-05-01T09:00:00Z",
                        "updated_at": "2026-05-02T10:30:00Z",
                    }
                ],
                "files": [
                    {
                        "id": "file-12345678",
                        "name": "diagram.txt",
                        "folder_id": None,
                        "size_bytes": 12,
                        "created_at": "2026-04-20T12:00:00Z",
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
                    "updated_at": "2026-05-03T08:15:00Z",
                }
            ],
        }

    def get_page(self, page_id):
        assert page_id == "page-12345678"
        return {"content_type": "markdown", "content_markdown": "# Plan\n", "content_html": ""}

    def download_file(self, file_id):
        assert file_id == "file-12345678"
        return b"diagram body"

    def get_skill_text(self, slug):
        assert slug == "demo-stash"
        return "# Demo Stash\n"

    def list_sources(self):
        return [
            {"type": "native_files", "source": "files", "display_name": "Files"},
            {
                "type": "gmail",
                "provider": "gmail",
                "source": "src-gmail-1",
                "display_name": "Gmail (demo@x.com)",
            },
        ]

    def list_source_entries(self, source, path=""):
        assert source == "src-gmail-1"
        self.source_entry_calls += 1
        return [
            {"path": "msg-1", "name": "Welcome email", "kind": "message", "external_ref": "gm-1"},
            {"path": "threads/msg-2", "name": "Nested note", "kind": "message"},
        ]

    def list_source_entries_page(self, source, path="", after=""):
        return self.list_source_entries(source, path), False

    def read_source_doc(self, source, ref):
        assert source == "src-gmail-1"
        return {"content": f"BODY of {ref}"}

    def get_transcript_events(self, session_id):
        assert session_id == "session-abc"
        return [{"role": "user", "content": "hello", "created_at": "2026-05-19T10:00:00Z"}]

    def export_transcript_jsonl(self, session_id):
        assert session_id == "session-abc"
        return '{"type":"user"}\n'

    def list_tables(self):
        return [{"id": "table-12345678", "name": "Ideas", "columns": [], "row_count": 1}]

    def get_table(self, table_id):
        assert table_id == "table-12345678"
        return {"id": table_id, "name": "Ideas", "columns": []}

    def list_table_rows(
        self,
        table_id,
        limit=1000,
        offset=0,
        sort_by="",
        sort_order="asc",
        filters="",
    ):
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


def test_vfs_exposes_user_sections():
    model = _model()

    assert set(model.list_dir("/")) == {
        "README.md",
        "files",
        "sessions",
        "skills",
        "tables",
        "sources",
    }
    assert model.read_file("/skills/Demo Skill.md") == b"# Demo Stash\n"
    assert b"hello" in model.read_file("/sessions/Fix login/transcript.md")
    assert b'"Name": "Mount"' in model.read_file("/tables/Ideas/rows.json")

    # Connected sources are mounted read-only under their provider folder;
    # native sources are skipped (files/sessions already appear above). A sole
    # connection collapses — its documents sit directly in the provider folder.
    assert model.list_dir("/sources") == ["gmail"]
    gmail = "/sources/gmail"
    assert "Welcome email" in model.list_dir(gmail)
    assert model.read_file(f"{gmail}/Welcome email") == b"BODY of msg-1"
    assert model.read_file(f"{gmail}/threads/Nested note") == b"BODY of threads/msg-2"


def test_vfs_loads_source_entries_lazily():
    # Listing source names must not fetch any source's contents — that's the
    # whole point: enumerating a 10k-doc source costs the same as a 1-doc one.
    client = FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    sources_path = "/sources"

    assert model.list_dir(sources_path) == ["gmail"]
    assert client.source_entry_calls == 0

    # Descending into a source materializes only that source, once.
    model.list_dir(f"{sources_path}/gmail")
    assert client.source_entry_calls == 1
    model.list_dir(f"{sources_path}/gmail")
    assert client.source_entry_calls == 1


class NestedPagesClient(FakeClient):
    # A Notion-style source where a page has both its own body and child pages.
    def list_sources(self):
        return [
            {
                "type": "notion",
                "provider": "notion",
                "source": "src-notion-1",
                "display_name": "Notes",
            }
        ]

    def list_source_entries(self, source, path=""):
        assert source == "src-notion-1"
        return [
            {"path": "Parent", "name": "Parent", "kind": "note"},
            {"path": "Parent/Child A", "name": "Child A", "kind": "note"},
            {"path": "Parent/Child B", "name": "Child B", "kind": "note"},
        ]

    def read_source_doc(self, source, ref):
        return {"content": f"BODY of {ref}"}


def test_vfs_keeps_children_of_a_page_that_has_its_own_body():
    # A page that is both content and a parent must not swallow its children.
    # It becomes a directory; its body lives in a same-named index file so the
    # children stay reachable alongside it.
    model = StashVfsModel(NestedPagesClient())
    model.refresh()
    # Sole notion connection collapses into /sources/notion (see _add_sources).
    parent = "/sources/notion/Parent"

    assert sorted(model.list_dir(parent)) == ["Child A", "Child B", "Parent"]
    assert model.read_file(f"{parent}/Parent") == b"BODY of Parent"
    assert model.read_file(f"{parent}/Child A") == b"BODY of Parent/Child A"
    assert model.read_file(f"{parent}/Child B") == b"BODY of Parent/Child B"


def test_vfs_reads_files_and_pages():
    model = _model()
    files_path = "/files"
    upload_name = next(name for name in model.list_dir(files_path) if name.startswith("diagram"))

    assert model.read_file(f"{files_path}/{upload_name}") == b"diagram body"

    folder_name = next(name for name in model.list_dir(files_path) if name.startswith("Notes"))
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(name for name in model.list_dir(folder_path) if name.startswith("Plan"))
    assert model.read_file(f"{folder_path}/{page_name}") == b"# Plan\n"


class DuplicateNameClient(FakeClient):
    """Two tables share a name — the backend allows it. Only the colliding pair
    should carry an id suffix; the uniquely-named table stays clean."""

    def list_tables(self):
        return [
            {"id": "aaaaaaaa-1111", "name": "Untitled table"},
            {"id": "bbbbbbbb-2222", "name": "Untitled table"},
            {"id": "cccccccc-3333", "name": "Roadmap"},
        ]


def test_vfs_suffixes_only_colliding_names():
    model = StashVfsModel(DuplicateNameClient())
    model.refresh()

    entries = set(model.list_dir("/tables"))

    # The unique name is clean; both members of the collision are suffixed with
    # their own id (not just the second one), so neither path depends on order.
    assert "Roadmap" in entries
    assert "Untitled table--aaaaaaaa" in entries
    assert "Untitled table--bbbbbbbb" in entries
    assert "Untitled table" not in entries


class AttachmentClient(FakeClient):
    """A file attached to a page (parent_page_id) is an internal of that
    document: the page stays a plain file with a stable path, and the
    attachment is reachable only through the download link in its body."""

    def get_overview(self):
        overview = super().get_overview()
        overview["files"]["pages"].append(
            {
                "id": "page-report99",
                "name": "Report",
                "content_type": "markdown",
                "folder_id": None,
                "created_at": "2026-06-01T09:00:00Z",
                "updated_at": "2026-06-02T10:30:00Z",
            }
        )
        overview["files"]["files"].append(
            {
                "id": "file-shot9999",
                "name": "shot.png",
                "folder_id": None,
                "parent_page_id": "page-report99",
                "size_bytes": 3,
                "created_at": "2026-06-01T09:05:00Z",
            }
        )
        return overview

    def get_page(self, page_id):
        if page_id == "page-report99":
            return {"content_type": "markdown", "content_markdown": "# Report\n"}
        return super().get_page(page_id)


def test_vfs_hides_page_attachments():
    model = StashVfsModel(AttachmentClient())
    model.refresh()

    entries = model.list_dir("/files")
    # The page keeps its plain-file path even though it owns an attachment.
    assert "Report.md" in entries
    assert "Report" not in entries
    assert model.read_file("/files/Report.md") == b"# Report\n"
    # The attachment is not a tree entry anywhere.
    assert "shot.png" not in entries
