import pytest

from stashai.skill_validation import render_skill_md, validate_skill_md


def test_valid_skill_requires_name_and_description() -> None:
    metadata = validate_skill_md(render_skill_md("release", "Prepare a product release."))

    assert metadata == {"name": "release", "description": "Prepare a product release."}


@pytest.mark.parametrize(
    ("content", "field"),
    [
        ("# body only", "name"),
        ("---\nname: release\ndescription:\n---\n", "description"),
    ],
)
def test_invalid_skill_reports_the_missing_field(content: str, field: str) -> None:
    with pytest.raises(ValueError, match=rf"non-empty `{field}`"):
        validate_skill_md(content)
