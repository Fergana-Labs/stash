"""Importing local skills at sign-up: every skill dir the user already has
lands in Stash once, skills Stash already holds are left alone, and each
imported skill is recorded in its root's sync state so the next
`stash skills sync` sees two copies in step rather than a never-synced
conflict."""

import json

from cli import main


def _skill_md(name: str) -> str:
    return (
        f"---\nname: {name}\ndescription: Use for {name} tasks.\n---\n# {name}\n\nDo the thing.\n"
    )


class _FakeClient:
    def __init__(self, existing: list[str]):
        self.skills: dict[str, dict] = {}
        for i, name in enumerate(existing):
            self.skills[f"existing-{i}"] = {"folder_name": name, "files": {}}
        self._next = 0

    def list_skills(self):
        return [{"folder_id": fid, "name": s["folder_name"]} for fid, s in self.skills.items()]

    def create_folder(self, name, parent_folder_id=None):
        self._next += 1
        fid = f"folder-{self._next}"
        self.skills[fid] = {"folder_name": name, "files": {}}
        return {"id": fid, "name": name}

    def replace_skill_contents(self, folder_id, files):
        self.skills[folder_id]["files"] = {rel: blob for rel, blob in files}
        return {"ok": True}

    def get_skill_contents(self, folder_id):
        s = self.skills[folder_id]
        pages = [
            {
                "name": rel,
                "content_type": "markdown",
                "content_markdown": blob.decode(),
                "folder_path": [],
            }
            for rel, blob in s["files"].items()
            if rel.endswith(".md")
        ]
        return {
            "folder_id": folder_id,
            "folder_name": s["folder_name"],
            "contents": {"pages": pages, "files": [], "folders": []},
        }


def _make_local_skill(root, name: str, extra: dict[str, str] | None = None):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_skill_md(name))
    for rel, text in (extra or {}).items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return skill_dir


def test_discovery_walks_every_known_root_and_first_root_wins(tmp_path, monkeypatch):
    claude = tmp_path / "claude-skills"
    agents = tmp_path / "agents-skills"
    _make_local_skill(claude, "deploy")
    _make_local_skill(agents, "deploy")
    _make_local_skill(agents, "review")
    (agents / "not-a-skill").mkdir()
    monkeypatch.setattr(
        main, "_LOCAL_SKILL_ROOTS", (str(claude), str(agents), str(tmp_path / "missing"))
    )

    found = main._discover_local_skills()

    assert set(found) == {"deploy", "review"}
    assert found["deploy"] == (claude, claude / "deploy")
    assert found["review"] == (agents, agents / "review")


def test_import_pushes_new_skills_skips_existing_and_records_sync_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        main, "_sync_state_path", lambda root: tmp_path / "state" / f"{root.name}.json"
    )
    root = tmp_path / "skills"
    _make_local_skill(root, "deploy", {"scripts/run.sh": "echo hi"})
    _make_local_skill(root, "review")
    found = {"deploy": (root, root / "deploy"), "review": (root, root / "review")}
    c = _FakeClient(existing=["Review"])

    summary = main._import_local_skills(c, found, fetch_bytes=lambda url: b"")

    assert summary == {"imported": ["deploy"], "skipped": ["review"], "failed": []}
    [(fid, pushed)] = [(fid, s) for fid, s in c.skills.items() if s["folder_name"] == "deploy"]
    assert set(pushed["files"]) == {"SKILL.md", "scripts/run.sh"}

    state = json.loads((tmp_path / "state" / "skills.json").read_text())
    assert state["deploy"]["folder_id"] == fid
    assert state["deploy"]["local_hash"] == main._hash_local_skill(root / "deploy")
    assert "review" not in state


def test_invalid_skill_md_is_reported_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_sync_state_path", lambda root: tmp_path / "state.json")
    root = tmp_path / "skills"
    broken = root / "broken"
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text("no frontmatter here")
    _make_local_skill(root, "fine")
    c = _FakeClient(existing=[])

    summary = main._import_local_skills(
        c,
        {"broken": (root, broken), "fine": (root, root / "fine")},
        fetch_bytes=lambda url: b"",
    )

    assert summary["imported"] == ["fine"]
    assert summary["skipped"] == []
    assert len(summary["failed"]) == 1 and summary["failed"][0].startswith("broken (")
