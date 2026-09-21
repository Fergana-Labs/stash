"""Add instructions to title-only Skills without rewriting their metadata or files."""

import hashlib
import json

from alembic import op
from sqlalchemy import text

revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None


def _with_instructions(markdown: str) -> str:
    # Freeze the parser here so future skill formats cannot change this migration.
    if not markdown.startswith("---\n"):
        raise ValueError("Skill instructions migration requires existing valid frontmatter")
    end = markdown.find("\n---", 4)
    if end == -1:
        raise ValueError("Skill instructions migration requires a closing frontmatter delimiter")
    metadata = {}
    for line in markdown[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            value = value.strip()
            metadata[key.strip()] = (
                json.loads(value) if value.startswith('"') and value.endswith('"') else value
            )
    name = metadata["name"].strip()
    description = metadata["description"].strip()
    if not name or not description:
        raise ValueError("Skill instructions migration requires a name and description")
    lines = markdown[end + 4 :].strip().splitlines()
    if lines and lines[0].strip() == f"# {name}":
        lines = lines[1:]
    if "\n".join(lines).strip():
        return markdown
    return markdown + "\n\n" + description + "\n"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT p.id, p.content_markdown FROM pages p "
            "JOIN folders f ON f.id = p.folder_id "
            "WHERE f.is_skill AND p.name = 'SKILL.md' AND p.deleted_at IS NULL"
        )
    ).mappings()
    for row in rows:
        original = row["content_markdown"]
        updated = _with_instructions(original)
        if updated == original:
            continue
        bind.execute(
            text(
                "UPDATE pages SET content_markdown = :content, content_hash = :hash, "
                "updated_at = now() WHERE id = :id"
            ),
            {
                "id": row["id"],
                "content": updated,
                "hash": hashlib.sha256(updated.encode()).hexdigest(),
            },
        )


def downgrade() -> None:
    # Added instructions are user content; a rollback must not remove later edits.
    pass
