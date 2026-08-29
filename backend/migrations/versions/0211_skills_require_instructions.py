"""Make instructions intrinsic to every stored skill.

Revision ID: 0211
Revises: 0210
"""

import hashlib
import json

from alembic import op
from sqlalchemy import text

revision = "0211"
down_revision = "0210"
branch_labels = None
depends_on = None


def _frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---"):
        return {}, markdown
    end = markdown.find("\n---", 3)
    if end == -1:
        return {}, markdown
    metadata = {}
    for line in markdown[3:end].strip("\n").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, markdown[end + 4 :].lstrip("\n")


def _valid_skill(markdown: str) -> bool:
    metadata, body = _frontmatter(markdown)
    instructions = body.strip().splitlines()
    if instructions and instructions[0].strip() == f"# {metadata.get('name', '').strip()}":
        instructions = instructions[1:]
    return bool(
        metadata.get("name", "").strip()
        and metadata.get("description", "").strip()
        and "\n".join(instructions).strip()
    )


def _template(name: str, description: str) -> str:
    return (
        f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description)}\n---\n\n"
        f"# {name}\n\n{description}\n"
    )


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT f.id AS folder_id, f.owner_user_id, f.created_by, f.name AS folder_name, "
            "p.id AS page_id, p.content_markdown "
            "FROM folders f LEFT JOIN pages p ON p.folder_id = f.id "
            "AND p.name = 'SKILL.md' AND p.deleted_at IS NULL WHERE f.is_skill"
        )
    ).mappings()
    for row in rows:
        markdown = row["content_markdown"] or ""
        if _valid_skill(markdown):
            continue
        metadata, _body = _frontmatter(markdown)
        name = metadata.get("name", "").strip() or row["folder_name"]
        description = metadata.get("description", "").strip()
        if not description:
            description = f"Use this skill for tasks related to {name}."
        repaired = _template(name, description)
        content_hash = hashlib.sha256(repaired.encode()).hexdigest()
        if row["page_id"]:
            bind.execute(
                text(
                    "UPDATE pages SET content_markdown = :content, content_hash = :hash, "
                    "updated_at = now() WHERE id = :page_id"
                ),
                {"content": repaired, "hash": content_hash, "page_id": row["page_id"]},
            )
            continue
        bind.execute(
            text(
                "INSERT INTO pages (owner_user_id, folder_id, name, content_markdown, "
                "content_hash, created_by, updated_by) VALUES "
                "(:owner, :folder, 'SKILL.md', :content, :hash, :actor, :actor)"
            ),
            {
                "owner": row["owner_user_id"],
                "folder": row["folder_id"],
                "content": repaired,
                "hash": content_hash,
                "actor": row["created_by"] or row["owner_user_id"],
            },
        )


def downgrade() -> None:
    pass
