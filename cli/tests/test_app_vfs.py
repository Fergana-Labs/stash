import shlex
from datetime import datetime

from cli.app_vfs import SkillAppVfsShell, _ls_time
from cli.client import StashError
from cli.mount import StashVfsModel
from cli.tests.test_mount_vfs import FakeClient


class DeadTranscriptClient(FakeClient):
    """A session whose transcript bodies 404 on fetch — the backend lists it
    but can no longer serve it. Mirrors the inconsistency that crashed grep."""

    def get_transcript_events(self, session_id):
        raise StashError(404, "Transcript not found")

    def export_transcript_jsonl(self, session_id):
        raise StashError(404, "Transcript not found")


class CountingClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.lazy_loads = 0

    def get_page(self, page_id):
        self.lazy_loads += 1
        return super().get_page(page_id)

    def download_file(self, file_id):
        self.lazy_loads += 1
        return super().download_file(file_id)

    def get_skill_text(self, slug):
        self.lazy_loads += 1
        return super().get_skill_text(slug)

    def get_transcript_events(self, session_id):
        self.lazy_loads += 1
        return super().get_transcript_events(session_id)

    def export_transcript_jsonl(self, session_id):
        self.lazy_loads += 1
        return super().export_transcript_jsonl(session_id)

    def get_table(self, table_id):
        self.lazy_loads += 1
        return super().get_table(table_id)

    def list_table_rows(
        self,
        table_id,
        limit=1000,
        offset=0,
        sort_by="",
        sort_order="asc",
        filters="",
    ):
        self.lazy_loads += 1
        return super().list_table_rows(
            table_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )


def _shell(client=None):
    client = client or FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    return SkillAppVfsShell(model), client


def _page_path(shell: SkillAppVfsShell) -> str:
    files_path = "/files"
    folder_name = next(
        name for name in shell.model.list_dir(files_path) if name.startswith("Notes")
    )
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(
        name for name in shell.model.list_dir(folder_path) if name.startswith("Plan")
    )
    return f"{folder_path}/{page_name}"


def test_app_vfs_runs_bash_shaped_navigation_commands():
    shell, _client = _shell()

    assert "files" in shell.run("ls /").stdout
    find_output = shell.run("find / -maxdepth 2 -type d").stdout
    assert "/files" in find_output


def test_app_vfs_supports_common_agent_listing_patterns():
    client = CountingClient()
    shell, _client = _shell(client)

    assert "files" in shell.run("ls -la /").stdout
    assert shell.run("find / -name '*.md' -type f").stdout.splitlines()
    tree_output = shell.run("tree / -L 2").stdout

    assert "files" in tree_output
    assert client.lazy_loads == 0


def test_app_vfs_surfaces_backend_timestamps_and_marks_unknown():
    """A node's modified time comes from the backend payload and flows through
    to `ls -l` and `stat`. A node the backend gave no timestamp for shows `-`,
    never a fabricated "now" — that distinction is the whole point of the
    feature, so it must hold even when some content lacks timestamps."""
    shell, _client = _shell()

    # A page carries distinct created/updated times straight from the backend.
    page_path = _page_path(shell)
    page_node = shell.model._get_node(page_path)
    expected = datetime.fromtimestamp(page_node.updated_at).isoformat()
    assert f"modified: {expected}" in shell.run(f"stat {page_path}").stdout
    assert _ls_time(page_node.updated_at) in shell.run(f"ls -l {page_path}").stdout

    # An uploaded file is immutable, so its modified-time is its creation time.
    file_name = next(
        name for name in shell.model.list_dir("/files") if name.startswith("diagram")
    )
    file_node = shell.model._get_node(f"/files/{file_name}")
    assert file_node.updated_at == file_node.created_at is not None

    # A synthetic directory the backend never timestamps shows "-", not a faked now.
    assert "modified: -" in shell.run("stat /files").stdout


def test_app_vfs_pipes_cat_to_sed_and_grep():
    shell, _client = _shell()
    page_path = _page_path(shell)

    assert shell.run(f"cat {shlex.quote(page_path)} | sed -n '1,1p'").stdout == "# Plan\n"

    result = shell.run("rg hello /")

    assert result.exit_code == 0
    assert "transcript.md" in result.stdout
    assert "transcript.md:" in shell.run("rg -n hello /").stdout


def test_app_vfs_grep_no_match_stops_and_chain():
    shell, _client = _shell()

    result = shell.run("rg missing-sentinel / && echo found")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == ""


def test_app_vfs_printf_supports_string_formats():
    shell, _client = _shell()

    result = shell.run("printf '%s\\n' first second")

    assert result.exit_code == 0
    assert result.stdout == "first\nsecond\n"
    assert shell.run("printf '100%%\\n'").stdout == "100%\n"


def test_app_vfs_command_chaining_preserves_all_stdout():
    shell, _client = _shell()

    result = shell.run("printf 'one\\n'; printf 'two\\n'")

    assert result.exit_code == 0
    assert result.stdout == "one\ntwo\n"


def test_app_vfs_sort_orders_dedupes_and_handles_numbers():
    shell, _client = _shell()

    assert shell.run("printf 'b\\na\\nc\\na\\n' | sort").stdout == "a\na\nb\nc\n"
    assert shell.run("printf 'b\\na\\nc\\na\\n' | sort -u").stdout == "a\nb\nc\n"
    # Numeric sort orders by value, not lexically (10 after 2, not before).
    assert shell.run("printf '10\\n2\\n1\\n' | sort -n").stdout == "1\n2\n10\n"
    assert shell.run("printf '1\\n2\\n10\\n' | sort -rn").stdout == "10\n2\n1\n"


def test_app_vfs_uniq_collapses_adjacent_runs():
    shell, _client = _shell()

    assert shell.run("printf 'a\\na\\nb\\na\\n' | uniq").stdout == "a\nb\na\n"
    assert shell.run("printf 'a\\na\\nb\\n' | uniq -c").stdout == "      2 a\n      1 b\n"
    assert shell.run("printf 'a\\na\\nb\\n' | uniq -d").stdout == "a\n"


def test_app_vfs_cut_selects_fields_and_chars():
    shell, _client = _shell()

    assert shell.run("printf 'a:b:c\\n' | cut -d: -f1,3").stdout == "a:c\n"
    assert shell.run("printf 'a,b,c\\n' | cut -d, -f2-").stdout == "b,c\n"
    assert shell.run("printf 'hello\\n' | cut -c1-3").stdout == "hel\n"
    # Fields are emitted in input order regardless of the spec order, like cut.
    assert shell.run("printf 'a:b:c\\n' | cut -d: -f3,1").stdout == "a:c\n"


def test_app_vfs_cut_passes_through_lines_without_the_delimiter():
    shell, _client = _shell()

    assert shell.run("printf 'no-delimiter-here\\n' | cut -d: -f2").stdout == "no-delimiter-here\n"


def test_app_vfs_grep_emits_context_lines():
    shell, _client = _shell()

    assert shell.run("printf 'l1\\nl2\\nM\\nl4\\n' | grep -A1 M").stdout == "M\nl4\n"
    assert shell.run("printf 'l1\\nl2\\nM\\nl4\\n' | grep -B1 M").stdout == "l2\nM\n"
    assert shell.run("printf 'l1\\nM\\nl3\\n' | grep -C1 M").stdout == "l1\nM\nl3\n"


def test_app_vfs_grep_separates_distant_context_groups():
    shell, _client = _shell()

    # Two matches far apart get their own context blocks split by a `--` line.
    result = shell.run("printf 'M\\nx\\ny\\nz\\nM\\n' | grep -A1 M")

    assert result.stdout == "M\nx\n--\nM\n"


def test_app_vfs_xargs_feeds_paths_with_spaces_into_a_command():
    shell, _client = _shell()

    # Skill titles contain spaces; xargs must treat each line as one argument.
    result = shell.run("find /skills -type f -name '*.md' | xargs cat")

    assert result.exit_code == 0
    assert result.stdout == "# Demo Stash\n"


def test_app_vfs_xargs_replaces_placeholder_and_batches():
    shell, _client = _shell()

    assert shell.run("printf 'x\\ny\\n' | xargs -I {} echo item={}").stdout == "item=x\nitem=y\n"
    assert shell.run("printf 'a\\nb\\n' | xargs -n1 echo").stdout == "a\nb\n"
    # Empty input runs nothing rather than invoking the command with no args.
    assert shell.run("printf '' | xargs cat").stdout == ""


def test_app_vfs_rejects_redirect_writes():
    shell, _client = _shell()
    page_path = _page_path(shell)

    result = shell.run(f"printf '# App edit\\n' > {shlex.quote(page_path)}")

    assert result.exit_code == 2
    assert "read-only" in result.stderr


def test_app_vfs_rejects_append_redirect_writes():
    shell, _client = _shell()
    page_path = _page_path(shell)

    result = shell.run(f"printf 'Second line\\n' >> {shlex.quote(page_path)}")

    assert result.exit_code == 2
    assert "read-only" in result.stderr


def test_app_vfs_tee_is_unsupported():
    shell, _client = _shell()
    page_path = _page_path(shell)

    result = shell.run(f"printf 'Second line\\n' | tee -a {shlex.quote(page_path)}")

    assert result.exit_code == 1
    assert "unsupported command: tee" in result.stderr


def test_app_vfs_reports_unsupported_commands():
    shell, _client = _shell()

    result = shell.run("python -c 'print(1)'")

    assert result.exit_code == 1
    assert "unsupported command: python" in result.stderr


def test_app_vfs_cd_updates_virtual_working_directory():
    shell, _client = _shell()

    result = shell.run("cd /files && pwd")

    assert result.stdout == "/files\n"
    assert result.cwd == "/files"


def test_app_vfs_grep_skips_unreadable_transcript_and_warns():
    shell, _client = _shell(DeadTranscriptClient())

    result = shell.run("grep -r Plan /")

    assert result.exit_code == 0
    assert "Plan" in result.stdout
    assert "Transcript not found" in result.stderr


def test_app_vfs_cat_unreadable_transcript_reports_error_without_traceback():
    shell, _client = _shell(DeadTranscriptClient())

    result = shell.run("cat '/sessions/Fix login/transcript.md'")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Transcript not found" in result.stderr


class PagedSourceClient(FakeClient):
    """A source whose listing spans several server pages. The VFS must keep
    following the `after` cursor until the listing is complete — stopping at
    one page silently hides most of a big source (a 6k-message Gmail, an
    800-file Drive)."""

    ENTRIES = [
        {"path": f"msg-{i:02d}", "name": f"Message {i}", "kind": "message"} for i in range(5)
    ]

    def list_source_entries_page(self, source, path="", after=""):
        assert source == "src-gmail-1"
        remaining = [e for e in self.ENTRIES if e["path"] > after]
        return remaining[:2], len(remaining) > 2


def test_source_listing_follows_pages_to_completion():
    shell, _client = _shell(PagedSourceClient())

    result = shell.run("find /sources/gmail -type f")

    for i in range(5):
        assert f"/sources/gmail/Message {i}" in result.stdout
    assert "INCOMPLETE" not in result.stderr


def test_find_warns_loudly_when_a_source_exceeds_the_materialization_ceiling(monkeypatch):
    monkeypatch.setattr("cli.mount.SOURCE_ENTRIES_MAX", 4)
    shell, _client = _shell(PagedSourceClient())

    result = shell.run("find /sources/gmail -type f")

    # The rows it did get still come back on stdout, uncorrupted by the warning.
    assert "/sources/gmail/Message 0" in result.stdout
    # The incompleteness is surfaced on stderr — not hidden, not mixed into the
    # file list where a pipe to `wc -l` would silently count it.
    assert "INCOMPLETE" in result.stderr
    assert "/sources/gmail" in result.stderr


def test_find_is_silent_when_a_source_listing_is_complete():
    shell, _client = _shell()  # base FakeClient reports not-truncated

    result = shell.run("find /sources/gmail -type f")

    assert "/sources/gmail/Welcome email" in result.stdout
    assert "INCOMPLETE" not in result.stderr


def test_stat_shows_external_ref_for_source_documents():
    shell, _client = _shell()

    result = shell.run("stat '/sources/gmail/Welcome email'")

    assert "external_ref: gm-1" in result.stdout


def test_stat_omits_external_ref_when_the_entry_has_none():
    shell, _client = _shell()

    result = shell.run("stat '/sources/gmail/threads/Nested note'")

    assert "external_ref" not in result.stdout
