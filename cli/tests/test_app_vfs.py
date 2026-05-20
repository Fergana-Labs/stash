import shlex

from cli.app_vfs import StashAppVfsShell
from cli.mount import StashVfsModel
from cli.tests.test_mount_vfs import FakeClient


def _shell(client=None):
    client = client or FakeClient()
    model = StashVfsModel(client)
    model.refresh()
    return StashAppVfsShell(model), client


def _page_path(shell: StashAppVfsShell) -> str:
    workspace_name = shell.model.list_dir("/workspaces")[0]
    files_path = f"/workspaces/{workspace_name}/files"
    folder_name = next(name for name in shell.model.list_dir(files_path) if name.startswith("Notes--"))
    folder_path = f"{files_path}/{folder_name}"
    page_name = next(name for name in shell.model.list_dir(folder_path) if name.startswith("Plan--"))
    return f"{folder_path}/{page_name}"


def test_app_vfs_runs_bash_shaped_navigation_commands():
    shell, _client = _shell()

    assert "workspaces" in shell.run("ls /").stdout
    find_output = shell.run("find /workspaces -maxdepth 2 -type d").stdout
    assert "/workspaces/Demo Workspace--workspac/files" in find_output


def test_app_vfs_pipes_cat_to_sed_and_grep():
    shell, _client = _shell()
    page_path = _page_path(shell)

    assert shell.run(f"cat {shlex.quote(page_path)} | sed -n '1,1p'").stdout == "# Plan\n"

    result = shell.run("rg hello /workspaces")

    assert result.exit_code == 0
    assert "transcript.md" in result.stdout


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


def test_app_vfs_cd_updates_virtual_working_directory():
    shell, _client = _shell()

    result = shell.run("cd /workspaces && pwd")

    assert result.stdout == "/workspaces\n"
    assert result.cwd == "/workspaces"
