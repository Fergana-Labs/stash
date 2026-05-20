import shlex

from cli.app_vfs import StashAppVfsShell
from cli.mount import StashVfsModel
from cli.tests.test_mount_vfs import FakeClient


class CountingClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.lazy_loads = 0

    def get_page(self, workspace_id, page_id):
        self.lazy_loads += 1
        return super().get_page(workspace_id, page_id)

    def download_ws_file(self, workspace_id, file_id):
        self.lazy_loads += 1
        return super().download_ws_file(workspace_id, file_id)

    def get_stash_text(self, slug):
        self.lazy_loads += 1
        return super().get_stash_text(slug)

    def get_transcript_events(self, workspace_id, session_id):
        self.lazy_loads += 1
        return super().get_transcript_events(workspace_id, session_id)

    def export_transcript_jsonl(self, workspace_id, session_id):
        self.lazy_loads += 1
        return super().export_transcript_jsonl(workspace_id, session_id)

    def get_table(self, workspace_id, table_id):
        self.lazy_loads += 1
        return super().get_table(workspace_id, table_id)

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
        self.lazy_loads += 1
        return super().list_table_rows(
            workspace_id,
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
    return StashAppVfsShell(model), client


def _page_path(shell: StashAppVfsShell) -> str:
    workspace_name = shell.model.list_dir("/workspaces")[0]
    files_path = f"/workspaces/{workspace_name}/files"
    folder_name = next(
        name for name in shell.model.list_dir(files_path) if name.startswith("Notes--")
    )
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(
        name for name in shell.model.list_dir(folder_path) if name.startswith("Plan--")
    )
    return f"{folder_path}/{page_name}"


def test_app_vfs_runs_bash_shaped_navigation_commands():
    shell, _client = _shell()

    assert "workspaces" in shell.run("ls /").stdout
    find_output = shell.run("find /workspaces -maxdepth 2 -type d").stdout
    assert "/workspaces/Demo Workspace--workspac/files" in find_output


def test_app_vfs_supports_common_agent_listing_patterns():
    client = CountingClient()
    shell, _client = _shell(client)

    assert "files" in shell.run("ls -la /workspaces/Demo\\ Workspace--workspac").stdout
    assert shell.run("find /workspaces -name '*.md' -type f").stdout.splitlines()
    tree_output = shell.run("tree /workspaces -L 2").stdout

    assert "Demo Workspace--workspac" in tree_output
    assert client.lazy_loads == 0


def test_app_vfs_pipes_cat_to_sed_and_grep():
    shell, _client = _shell()
    page_path = _page_path(shell)

    assert shell.run(f"cat {shlex.quote(page_path)} | sed -n '1,1p'").stdout == "# Plan\n"

    result = shell.run("rg hello /workspaces")

    assert result.exit_code == 0
    assert "transcript.md" in result.stdout
    assert "transcript.md:" in shell.run("rg -n hello /workspaces").stdout


def test_app_vfs_writes_existing_writable_pages_with_redirect():
    shell, client = _shell()
    page_path = _page_path(shell)

    result = shell.run(f"printf '# App edit\\n' > {shlex.quote(page_path)}")

    assert result.exit_code == 0
    assert client.page_updates == [
        (
            "workspace-12345678",
            "page-12345678",
            {"content": "# App edit\n"},
        )
    ]


def test_app_vfs_appends_existing_writable_pages_with_tee():
    shell, client = _shell()
    page_path = _page_path(shell)

    result = shell.run(f"printf 'Second line\\n' | tee -a {shlex.quote(page_path)}")

    assert result.exit_code == 0
    assert result.stdout == "Second line\n"
    assert client.page_updates == [
        (
            "workspace-12345678",
            "page-12345678",
            {"content": "# Plan\nSecond line\n"},
        )
    ]


def test_app_vfs_refuses_read_only_writes():
    shell, client = _shell()

    result = shell.run("printf 'Nope\\n' > /README.md")

    assert result.exit_code == 1
    assert "/README.md" in result.stderr
    assert client.page_updates == []


def test_app_vfs_reports_unsupported_commands():
    shell, _client = _shell()

    result = shell.run("python -c 'print(1)'")

    assert result.exit_code == 1
    assert "unsupported command: python" in result.stderr


def test_app_vfs_cd_updates_virtual_working_directory():
    shell, _client = _shell()

    result = shell.run("cd /workspaces && pwd")

    assert result.stdout == "/workspaces\n"
    assert result.cwd == "/workspaces"
