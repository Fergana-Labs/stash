"""`stash skills install` materializes a public skill into a local skills
directory — the bridge from Discover to the agent's ~/.claude/skills. These
lock in the layout rules: SKILL.md keeps its exact name, extensionless pages
gain one, nested folder_paths become subdirectories, binaries download, and
re-install replaces only directories that already look like a skill."""

import pytest
import typer

from cli import main


def _detail() -> dict:
    return {
        "skill": {"title": "Hivemind Memory"},
        "folder_name": "hivemind-memory",
        "contents": {
            "subfolders": [{"name": "references", "path": ["references"]}],
            "pages": [
                {
                    "name": "SKILL.md",
                    "content_type": "markdown",
                    "content_markdown": (
                        "---\nname: hivemind-memory\n"
                        "description: Recall shared team knowledge.\n---\nBody."
                    ),
                    "content_html": "",
                    "folder_path": [],
                },
                {
                    "name": "Notes",
                    "content_type": "markdown",
                    "content_markdown": "# notes",
                    "content_html": "",
                    "folder_path": [],
                },
                {
                    "name": "guide.md",
                    "content_type": "markdown",
                    "content_markdown": "# guide",
                    "content_html": "",
                    "folder_path": ["references"],
                },
            ],
            "files": [
                {"name": "logo.png", "url": "https://files/logo", "folder_path": []},
                {"name": "broken.bin", "url": None, "folder_path": []},
            ],
            "tables": [],
        },
    }


def _fetch(url: str) -> bytes:
    return b"PNG:" + url.encode()


def test_install_writes_skill_folder(tmp_path) -> None:
    target, written = main._materialize_skill(_detail(), tmp_path, _fetch)

    assert target == tmp_path / "hivemind-memory"
    # SKILL.md keeps its exact name because agent harnesses require it.
    assert (target / "SKILL.md").read_text().startswith("---\nname: hivemind-memory")
    # Extensionless pages gain .md so they're readable files on disk.
    assert (target / "Notes.md").read_text() == "# notes"
    # folder_path nests.
    assert (target / "references" / "guide.md").read_text() == "# guide"
    # Binaries download; URL-less files are skipped, not fatal.
    assert (target / "logo.png").read_bytes() == b"PNG:https://files/logo"
    assert not (target / "broken.bin").exists()
    assert written == 4


def test_reinstall_replaces_previous_copy(tmp_path) -> None:
    main._materialize_skill(_detail(), tmp_path, _fetch)
    stale = tmp_path / "hivemind-memory" / "stale.md"
    stale.write_text("old")

    main._materialize_skill(_detail(), tmp_path, _fetch)

    assert not stale.exists()
    assert (tmp_path / "hivemind-memory" / "SKILL.md").exists()


def test_invalid_reinstall_preserves_previous_copy(tmp_path) -> None:
    main._materialize_skill(_detail(), tmp_path, _fetch)
    existing = tmp_path / "hivemind-memory" / "SKILL.md"
    original = existing.read_text()
    detail = _detail()
    detail["contents"]["pages"][0]["content_markdown"] = "# invalid"

    with pytest.raises(ValueError, match="non-empty `name`"):
        main._materialize_skill(detail, tmp_path, _fetch)

    assert existing.read_text() == original


def test_install_never_clobbers_a_non_skill_dir(tmp_path) -> None:
    (tmp_path / "hivemind-memory").mkdir()
    (tmp_path / "hivemind-memory" / "precious.txt").write_text("keep me")

    with pytest.raises(typer.Exit):
        main._materialize_skill(_detail(), tmp_path, _fetch)

    assert (tmp_path / "hivemind-memory" / "precious.txt").read_text() == "keep me"


def test_safe_dirname() -> None:
    assert main._safe_skill_dirname("theme-factory") == "theme-factory"
    assert main._safe_skill_dirname("a/b: c") == "a-b- c"
    # Collision-suffixed folder names ("name (2)") stay readable on disk.
    assert main._safe_skill_dirname("hivemind-memory (2)") == "hivemind-memory (2)"
    assert main._safe_skill_dirname("...") == "skill"
