"""Validation for agent-compatible SKILL.md files."""

from __future__ import annotations

import json


def parse_frontmatter(markdown: str) -> tuple[dict, str]:
    """Parse the flat YAML frontmatter fields used by agent skills."""
    if not markdown.startswith("---"):
        return {}, markdown
    end = markdown.find("\n---", 3)
    if end == -1:
        return {}, markdown
    raw = markdown[3:end].strip("\n")
    body = markdown[end + 4 :].lstrip("\n")
    metadata: dict = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.lower() in ("true", "false"):
            metadata[key] = value.lower() == "true"
        elif value.startswith('"') and value.endswith('"'):
            metadata[key] = json.loads(value)
        else:
            metadata[key] = value
    return metadata, body


def validate_skill_md(markdown: str) -> dict:
    """Return skill metadata or raise when required fields are absent."""
    metadata, _body = parse_frontmatter(markdown)
    for field in ("name", "description"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"SKILL.md requires a non-empty `{field}` field")
    return metadata


def render_skill_md(name: str, description: str) -> str:
    """Create a minimal valid SKILL.md without inventing metadata."""
    for field, value in (("name", name), ("description", description)):
        if not value.strip():
            raise ValueError(f"SKILL.md requires a non-empty `{field}` field")
        if "\n" in value or "\r" in value:
            raise ValueError(f"SKILL.md `{field}` must be a single line")
    return (
        f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description)}\n---\n\n# {name}\n"
    )
