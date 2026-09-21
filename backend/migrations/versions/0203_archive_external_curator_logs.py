"""Move external curator logs out of customer-readable wikis.

Both the current Log and the older _system/changelog contain private details.
Preserve their contents in an unshared workspace folder and remove references
from shared pages. Future audit history lives in the curator's run transcript.

Revision ID: 0203
Revises: 0202
"""

import hashlib
import re

from alembic import op
from sqlalchemy import text

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    workspaces = (
        bind.execute(
            text(
                "SELECT scope_user_id, external_wiki_folder_id FROM workspaces "
                "WHERE external_wiki_folder_id IS NOT NULL"
            )
        )
        .mappings()
        .all()
    )
    for workspace in workspaces:
        pages = (
            bind.execute(
                text(
                    "WITH RECURSIVE tree AS ("
                    "SELECT id, ''::text AS path FROM folders WHERE id = :root "
                    "UNION ALL SELECT f.id, tree.path || f.name || '/' FROM folders f "
                    "JOIN tree ON f.parent_folder_id = tree.id"
                    ") SELECT p.id, p.name, p.content_type, p.content_markdown, p.deleted_at, "
                    "tree.path FROM pages p JOIN tree ON p.folder_id = tree.id"
                ),
                {"root": workspace["external_wiki_folder_id"]},
            )
            .mappings()
            .all()
        )
        logs = [p for p in pages if p["name"].lower() in ("log", "changelog")]
        if not logs:
            continue
        archive_id = bind.execute(
            text(
                "INSERT INTO folders (owner_user_id, created_by, name, public_permission) "
                "VALUES (:owner, :owner, 'Curator log archive', 'none') RETURNING id"
            ),
            {"owner": workspace["scope_user_id"]},
        ).scalar_one()
        log_ids = {p["id"] for p in logs}
        for page in logs:
            bind.execute(
                text(
                    "UPDATE pages SET folder_id = :archive, name = :name, "
                    "public_permission = 'none', end_user_id = NULL, updated_at = now() "
                    "WHERE id = :id"
                ),
                {"archive": archive_id, "name": f"{page['name']} ({page['id']})", "id": page["id"]},
            )
            bind.execute(
                text("DELETE FROM shares WHERE object_type = 'page' AND object_id = :id"),
                {"id": page["id"]},
            )
        # Drop reference lines, not a redirect: customers must not be invited
        # to retrieve a private archive through the developer's credential.
        references = [str(page_id) for page_id in log_ids]
        references.extend(f"/memory/{p['path']}{p['name']}.md" for p in logs)
        refs = re.compile("|".join(re.escape(ref) for ref in references))
        for page in pages:
            if page["id"] in log_ids or page["deleted_at"] is not None:
                continue
            content = page["content_markdown"]
            if not refs.search(content):
                continue
            if page["content_type"] != "markdown":
                raise ValueError(f"Archive reference in non-markdown page {page['id']}")
            cleaned = "".join(
                line for line in content.splitlines(keepends=True) if not refs.search(line)
            )
            bind.execute(
                text(
                    "UPDATE pages SET content_markdown = :content, content_hash = :hash, "
                    "embedding = NULL, embed_stale = TRUE, updated_at = now() WHERE id = :id"
                ),
                {
                    "content": cleaned,
                    "hash": hashlib.sha256(cleaned.encode()).hexdigest(),
                    "id": page["id"],
                },
            )


def downgrade() -> None:
    raise NotImplementedError("Restoring curator logs to the shared wiki would expose private data")
