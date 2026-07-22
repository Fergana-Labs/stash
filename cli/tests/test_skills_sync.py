"""`stash skills sync` keeps the local skills directory and the user's cloud
skills in step. These lock in the three-way semantics: cloud-only skills
materialize locally, local edits to synced skills push back, edits on both
sides conflict loudly instead of clobbering either, and untracked local skills
only auto-push in project mode."""

import pytest

from cli import main


def _skill(body: str) -> bytes:
    return f"---\nname: deploy\ndescription: Deploy the application.\n---\n\n{body}".encode()


class _FakeSyncClient:
    """In-memory skills store: folder_id -> {folder_name, files{relpath: bytes}}."""

    def __init__(self):
        self.skills: dict[str, dict] = {}
        self._next = 0

    def add_remote_skill(self, name: str, files: dict[str, bytes]) -> str:
        folder_id = self.create_folder(name, is_skill=True)["id"]
        self.skills[folder_id]["files"] = dict(files)
        return folder_id

    def list_skills(self):
        return [{"folder_id": fid, "name": s["folder_name"]} for fid, s in self.skills.items()]

    def get_skill_contents(self, folder_id):
        s = self.skills[folder_id]
        pages, files = [], []
        for rel, blob in s["files"].items():
            dirpath, _, fname = rel.rpartition("/")
            folder_path = dirpath.split("/") if dirpath else []
            if fname.endswith(".md"):
                pages.append(
                    {
                        "name": fname,
                        "content_type": "markdown",
                        "content_markdown": blob.decode(),
                        "content_html": "",
                        "folder_path": folder_path,
                    }
                )
            else:
                files.append(
                    {
                        "name": fname,
                        "url": f"fake://{folder_id}/{rel}",
                        "size_bytes": len(blob),
                        "folder_path": folder_path,
                    }
                )
        return {
            "folder_id": folder_id,
            "folder_name": s["folder_name"],
            "contents": {"subfolders": [], "pages": pages, "files": files, "tables": []},
        }

    def replace_skill_contents(self, folder_id, files):
        self.skills[folder_id]["files"] = dict(files)
        return {"folder_id": folder_id, "items": len(files)}

    def create_folder(self, name, *, is_skill=False):
        assert is_skill
        folder_id = f"folder-{self._next}"
        self._next += 1
        self.skills[folder_id] = {"folder_name": name, "files": {}}
        return {"id": folder_id}

    def fetch_bytes(self, url: str) -> bytes:
        folder_id, _, rel = url.removeprefix("fake://").partition("/")
        return self.skills[folder_id]["files"][rel]


def _sync(c, root, state, push_new=False):
    return main._sync_skills(c, root, state, push_new, c.fetch_bytes)


def test_cloud_skill_materializes_locally(tmp_path):
    c = _FakeSyncClient()
    c.add_remote_skill("deploy", {"SKILL.md": _skill("# deploy"), "scripts/run.sh": b"#!/bin/sh"})

    summary, state = _sync(c, tmp_path, {})

    assert summary["pulled"] == ["deploy"]
    assert (tmp_path / "deploy" / "SKILL.md").read_bytes() == _skill("# deploy")
    assert (tmp_path / "deploy" / "scripts" / "run.sh").read_bytes() == b"#!/bin/sh"
    assert "deploy" in state


def test_local_edit_pushes_and_remote_edit_pulls(tmp_path):
    c = _FakeSyncClient()
    fid = c.add_remote_skill("deploy", {"SKILL.md": _skill("# v1")})
    _summary, state = _sync(c, tmp_path, {})

    (tmp_path / "deploy" / "SKILL.md").write_bytes(_skill("# v2 local"))
    summary, state = _sync(c, tmp_path, state)
    assert summary["pushed"] == ["deploy"]
    assert c.skills[fid]["files"]["SKILL.md"] == _skill("# v2 local")

    c.skills[fid]["files"]["SKILL.md"] = _skill("# v3 remote")
    summary, state = _sync(c, tmp_path, state)
    assert summary["pulled"] == ["deploy"]
    assert (tmp_path / "deploy" / "SKILL.md").read_bytes() == _skill("# v3 remote")

    summary, _state = _sync(c, tmp_path, state)
    assert summary["unchanged"] == ["deploy"]


def test_both_sides_changed_conflicts_without_clobbering(tmp_path):
    c = _FakeSyncClient()
    fid = c.add_remote_skill("deploy", {"SKILL.md": _skill("# v1")})
    _summary, state = _sync(c, tmp_path, {})

    (tmp_path / "deploy" / "SKILL.md").write_bytes(_skill("# local edit"))
    c.skills[fid]["files"]["SKILL.md"] = _skill("# remote edit")

    summary, state = _sync(c, tmp_path, state)

    assert len(summary["conflicts"]) == 1
    assert (tmp_path / "deploy" / "SKILL.md").read_bytes() == _skill("# local edit")
    assert c.skills[fid]["files"]["SKILL.md"] == _skill("# remote edit")
    # The conflict stays pending — the next run reports it again.
    summary, _state = _sync(c, tmp_path, state)
    assert len(summary["conflicts"]) == 1


def test_new_local_skill_pushes_only_in_project_mode(tmp_path):
    c = _FakeSyncClient()
    (tmp_path / "my-skill").mkdir()
    (tmp_path / "my-skill" / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: My skill.\n---\n\n# mine"
    )

    summary, _state = _sync(c, tmp_path, {}, push_new=False)
    assert summary["pushed"] == []
    assert any("my-skill" in note for note in summary["ignored"])

    summary, _state = _sync(c, tmp_path, {}, push_new=True)
    assert summary["pushed"] == ["my-skill"]
    only = next(iter(c.skills.values()))
    assert b"description: My skill." in only["files"]["SKILL.md"]


def test_untracked_name_collision_is_a_conflict(tmp_path):
    c = _FakeSyncClient()
    c.add_remote_skill("deploy", {"SKILL.md": _skill("# theirs")})
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "SKILL.md").write_bytes(_skill("# mine, never synced"))

    summary, _state = _sync(c, tmp_path, {})

    assert len(summary["conflicts"]) == 1
    assert (tmp_path / "deploy" / "SKILL.md").read_bytes() == _skill("# mine, never synced")


def test_invalid_cloud_skill_is_not_materialized(tmp_path):
    c = _FakeSyncClient()
    c.add_remote_skill("deploy", {"SKILL.md": b"---\nname: deploy\ndescription:\n---\n"})

    with pytest.raises(ValueError, match="non-empty `description`"):
        _sync(c, tmp_path, {})

    assert not (tmp_path / "deploy").exists()
