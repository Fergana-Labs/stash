import importlib

import pytest

from backend.services import skill_service


def test_skill_template_round_trips_yaml_sensitive_metadata():
    markdown = skill_service.skill_md_template(
        "Release: web",
        "Use for deploys:\nproduction only.",
    )

    metadata, body = skill_service.parse_frontmatter(markdown)

    assert metadata == {
        "name": "Release: web",
        "description": "Use for deploys:\nproduction only.",
    }
    assert body == "# Release: web\n"
    skill_service.validate_skill_md(markdown)


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        ("---\nname: deploy\ndescription: \n---\n", "nonblank description"),
        (
            f"---\nname: {'x' * 65}\ndescription: Deploy.\n---\n",
            "at most 64 characters",
        ),
        (
            f"---\nname: deploy\ndescription: {'x' * 1025}\n---\n",
            "at most 1024 characters",
        ),
    ],
)
def test_skill_validation_rejects_metadata_codex_cannot_load(markdown, message):
    with pytest.raises(ValueError, match=message):
        skill_service.validate_skill_md(markdown)


def test_skill_migration_repairs_blank_legacy_metadata():
    migration = importlib.import_module("backend.migrations.versions.0180_valid_skill_frontmatter")

    migrated = migration._valid_markdown(
        "---\nname: Legacy skill\ndescription: \n---\n\n# Instructions\n",
        "Legacy skill",
        "",
    )

    metadata, body = skill_service.parse_frontmatter(migrated)
    assert metadata == {
        "name": "Legacy skill",
        "description": "Use this skill for tasks related to Legacy skill.",
    }
    assert body == "# Instructions\n"
    skill_service.validate_skill_md(migrated)
