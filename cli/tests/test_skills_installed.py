"""Installed-skill tracking: skills installed from Discover or a followed
share auto-update on `stash skills sync` — the manifest is what separates
"skills I own" (three-way synced) from "skills I installed" (cloud is the
source of truth). These lock in: changed installs refresh, unchanged ones
don't re-materialize, follow mode installs newly shared skills exactly once,
and installed dirs never get pushed to the user's own Stash in project mode.
"""

from cli import main


def _contents(files: dict[str, str]) -> dict:
    pages = [
        {
            "name": name,
            "content_type": "markdown",
            "content_markdown": body,
            "content_html": "",
            "folder_path": [],
        }
        for name, body in files.items()
    ]
    return {"subfolders": [], "pages": pages, "files": [], "tables": []}


class _FakeInstallClient:
    def __init__(self):
        self.public: dict[str, dict] = {}
        self.shared: dict[str, dict] = {}

    def add_public(self, slug: str, folder_name: str, files: dict[str, str]) -> None:
        self.public[slug] = {
            "skill": {"title": folder_name},
            "folder_name": folder_name,
            "contents": _contents(files),
        }

    def add_shared(self, folder_id: str, folder_name: str, files: dict[str, str]) -> None:
        self.shared[folder_id] = {
            "folder_id": folder_id,
            "folder_name": folder_name,
            "contents": _contents(files),
        }

    def get_public_skill(self, slug):
        return self.public[slug]

    def list_shared_skills(self):
        return [{"folder_id": fid, "name": s["folder_name"]} for fid, s in self.shared.items()]

    def get_shared_skill_contents(self, folder_id):
        return self.shared[folder_id]

    def fetch_bytes(self, url: str) -> bytes:
        raise AssertionError("no binary files in these fixtures")


def _install(c, slug: str, root, entry) -> None:
    detail = c.get_public_skill(slug)
    target, _ = main._materialize_skill(detail, root, c.fetch_bytes)
    entry["skills"][target.name] = {
        "slug": slug,
        "remote_hash": main._hash_remote_contents(detail["contents"]),
    }


def test_changed_install_refreshes_and_unchanged_does_not(tmp_path):
    c = _FakeInstallClient()
    c.add_public("pdf-tools", "pdf-tools", {"SKILL.md": "v1"})
    entry = {"skills": {}, "follow_shared": False}
    _install(c, "pdf-tools", tmp_path, entry)

    updated, notes = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == [] and notes == []

    c.add_public("pdf-tools", "pdf-tools", {"SKILL.md": "v2"})
    updated, _ = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == ["pdf-tools"]
    assert (tmp_path / "pdf-tools" / "SKILL.md").read_text() == "v2"


def test_deleted_local_copy_is_reinstalled(tmp_path):
    c = _FakeInstallClient()
    c.add_public("pdf-tools", "pdf-tools", {"SKILL.md": "v1"})
    entry = {"skills": {}, "follow_shared": False}
    _install(c, "pdf-tools", tmp_path, entry)

    import shutil

    shutil.rmtree(tmp_path / "pdf-tools")
    updated, _ = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == ["pdf-tools"]
    assert (tmp_path / "pdf-tools" / "SKILL.md").exists()


def test_follow_installs_new_shared_skill_exactly_once(tmp_path):
    c = _FakeInstallClient()
    c.add_shared("f-1", "team-deploys", {"SKILL.md": "runbook"})
    entry = {"skills": {}, "follow_shared": True}

    updated, notes = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == ["team-deploys (newly shared)"]
    assert (tmp_path / "team-deploys" / "SKILL.md").read_text() == "runbook"
    assert entry["skills"]["team-deploys"]["shared_folder_id"] == "f-1"

    updated, notes = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == [] and notes == []


def test_follow_off_ignores_shared_skills(tmp_path):
    c = _FakeInstallClient()
    c.add_shared("f-1", "team-deploys", {"SKILL.md": "runbook"})
    entry = {"skills": {}, "follow_shared": False}

    updated, _ = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == []
    assert not (tmp_path / "team-deploys").exists()


def test_new_share_colliding_with_local_dir_is_skipped_loudly(tmp_path):
    c = _FakeInstallClient()
    c.add_shared("f-1", "notes", {"SKILL.md": "theirs"})
    (tmp_path / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "SKILL.md").write_text("mine")
    entry = {"skills": {}, "follow_shared": True}

    updated, notes = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == []
    assert notes and "collides" in notes[0]
    assert (tmp_path / "notes" / "SKILL.md").read_text() == "mine"


def test_cloud_rename_moves_the_install(tmp_path):
    c = _FakeInstallClient()
    c.add_public("pdf-tools", "pdf-tools", {"SKILL.md": "v1"})
    entry = {"skills": {}, "follow_shared": False}
    _install(c, "pdf-tools", tmp_path, entry)

    c.add_public("pdf-tools", "pdf-toolkit", {"SKILL.md": "v2"})
    updated, _ = main._sync_installed(c, tmp_path, entry, c.fetch_bytes)
    assert updated == ["pdf-toolkit"]
    assert not (tmp_path / "pdf-tools").exists()
    assert (tmp_path / "pdf-toolkit" / "SKILL.md").read_text() == "v2"
    assert set(entry["skills"]) == {"pdf-toolkit"}


def test_installed_skill_never_pushes_to_own_stash_in_project_mode(tmp_path):
    from cli.tests.test_skills_sync import _FakeSyncClient

    c = _FakeSyncClient()
    (tmp_path / "installed-one").mkdir(parents=True)
    (tmp_path / "installed-one" / "SKILL.md").write_text("someone else's")

    summary, state = main._sync_skills(
        c, tmp_path, {}, push_new=True, fetch_bytes=c.fetch_bytes, skip={"installed-one"}
    )
    assert summary["pushed"] == []
    assert c.skills == {}


def test_installed_skill_shadowing_owned_skill_conflicts_loudly(tmp_path):
    from cli.tests.test_skills_sync import _FakeSyncClient

    c = _FakeSyncClient()
    c.add_remote_skill("notes", {"SKILL.md": b"owned copy"})
    (tmp_path / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "SKILL.md").write_text("installed copy")

    summary, _ = main._sync_skills(
        c, tmp_path, {}, push_new=False, fetch_bytes=c.fetch_bytes, skip={"notes"}
    )
    assert summary["conflicts"] and "shadows" in summary["conflicts"][0]
    assert (tmp_path / "notes" / "SKILL.md").read_text() == "installed copy"
