"""Repair pre-existing Skills before the catalog requires valid frontmatter.

0223 only repaired curation roots. Ordinary Skills could still have a missing,
deleted, or invalid SKILL.md, including Skills disabled for agents. Repair
them once without changing membership, sharing, or the instruction body.
"""

import hashlib
import json

from alembic import op
from sqlalchemy import text

revision = "0228"
down_revision = "0227"
branch_labels = None
depends_on = None


def _repair(markdown: str, folder_name: str, published_description: str) -> str:
    # Frozen frontmatter rules: migrations must not depend on live validators.
    lines = []
    suffix = "\n\n" + markdown
    if markdown.startswith("---"):
        end = markdown.find("\n---", 3)
        if end != -1:
            lines = markdown[3:end].strip("\n").splitlines()
            suffix = markdown[end + 4 :]
    values = {}
    for line in lines:
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        elif value.lower() in ("true", "false"):
            value = value.lower() == "true"
        values[key.strip()] = value
    name = str(values.get("name", "")).strip()
    description = str(values.get("description", "")).strip()
    if (
        isinstance(values.get("name"), str)
        and isinstance(values.get("description"), str)
        and 0 < len(name) <= 64
        and 0 < len(description) <= 1024
    ):
        return markdown

    name = (name or folder_name.strip())[:64]
    if not name:
        raise ValueError("Cannot repair a Skill with no name in either its folder or frontmatter")
    description = (
        description
        or published_description.strip()
        or f"Use this skill for tasks related to {name}."
    )[:1024]
    retained = [
        line for line in lines if line.partition(":")[0].strip() not in ("name", "description")
    ]
    metadata = [f"name: {json.dumps(name)}", f"description: {json.dumps(description)}", *retained]
    return "---\n" + "\n".join(metadata) + "\n---" + suffix


def upgrade() -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            text(
                "SELECT f.id AS folder_id, f.owner_user_id, f.created_by, f.name AS folder_name, "
                "p.id AS page_id, p.content_markdown, eu.id AS end_user_id, "
                "COALESCE(s.description, '') AS published_description "
                "FROM folders f "
                "LEFT JOIN pages p ON p.folder_id=f.id AND p.name='SKILL.md' AND p.deleted_at IS NULL "
                "LEFT JOIN skills s ON s.folder_id=f.id "
                "LEFT JOIN end_users eu ON eu.skill_folder_id=f.id "
                "WHERE f.is_skill"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        markdown = row["content_markdown"] or ""
        content = _repair(markdown, row["folder_name"], row["published_description"])
        if row["page_id"] is not None and content == markdown:
            continue
        params = {
            "page": row["page_id"],
            "folder": row["folder_id"],
            "owner": row["owner_user_id"],
            "creator": row["created_by"],
            "end_user": row["end_user_id"],
            "content": content,
            "hash": hashlib.sha256(content.encode()).hexdigest(),
        }
        if row["page_id"] is not None:
            bind.execute(
                text(
                    "UPDATE pages SET content_markdown=:content, content_hash=:hash, "
                    "embed_stale=true, updated_at=now() WHERE id=:page"
                ),
                params,
            )
        else:
            # Do not resurrect a deleted document. It remains in Trash, and the
            # existing Skill gets a new entry point with no invented instructions.
            bind.execute(
                text(
                    "INSERT INTO pages (owner_user_id, folder_id, end_user_id, name, "
                    "content_markdown, content_hash, created_by, updated_by, embed_stale) "
                    "VALUES (:owner, :folder, :end_user, 'SKILL.md', :content, :hash, :creator, :creator, true)"
                ),
                params,
            )


def downgrade() -> None:
    raise NotImplementedError("Restore a database backup to reverse the Skill metadata repair.")
