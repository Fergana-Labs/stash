"""Make every stored SKILL.md valid for agent skill loaders.

Revision ID: 0182
Revises: 0181
"""

import hashlib
import json

from alembic import op
from sqlalchemy import text

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None

MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024


def _metadata_lines(markdown: str) -> tuple[list[str], str]:
    if not markdown.startswith("---\n"):
        return [], markdown
    end = markdown.find("\n---", 4)
    if end == -1:
        return [], markdown
    return markdown[4:end].splitlines(), markdown[end + 4 :].lstrip("\n")


def _metadata_value(lines: list[str], key: str) -> str:
    prefix = f"{key}:"
    line = next((line for line in lines if line.startswith(prefix)), "")
    value = line.removeprefix(prefix).strip()
    if value.startswith('"') and value.endswith('"'):
        return str(json.loads(value))
    return value


def _valid_markdown(markdown: str, folder_name: str, published_description: str) -> str:
    lines, body = _metadata_lines(markdown)
    name = (_metadata_value(lines, "name") or folder_name).strip()[:MAX_SKILL_NAME_LENGTH]
    description = _metadata_value(lines, "description").strip()
    if not description:
        description = (published_description or "").strip()
    if not description:
        description = f"Use this skill for tasks related to {name}."
    description = description[:MAX_SKILL_DESCRIPTION_LENGTH]

    retained = [
        line
        for line in lines
        if not line.startswith("name:") and not line.startswith("description:")
    ]
    metadata = [f"name: {json.dumps(name)}", f"description: {json.dumps(description)}", *retained]
    suffix = f"\n\n{body}" if body else "\n"
    return f"---\n{'\n'.join(metadata)}\n---{suffix}"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT p.id, p.content_markdown, f.name AS folder_name, "
            "COALESCE(s.description, '') AS published_description "
            "FROM pages p JOIN folders f ON f.id = p.folder_id "
            "LEFT JOIN skills s ON s.folder_id = f.id "
            "WHERE p.name = 'SKILL.md' AND p.deleted_at IS NULL"
        )
    ).mappings()
    for row in rows:
        markdown = row["content_markdown"] or ""
        valid = _valid_markdown(markdown, row["folder_name"], row["published_description"])
        if valid == markdown:
            continue
        bind.execute(
            text(
                "UPDATE pages SET content_markdown = :content, "
                "content_hash = :content_hash, updated_at = now() "
                "WHERE id = :page_id"
            ),
            {
                "content": valid,
                "content_hash": hashlib.sha256(valid.encode()).hexdigest(),
                "page_id": row["id"],
            },
        )


def downgrade() -> None:
    pass
