"""Make every existing curation destination a Skill without replacing its knowledge."""

import hashlib
import json

from alembic import op
from sqlalchemy import text

revision = "0223"
down_revision = "0222"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("folders", "is_memory", "is_curated_skill"),
    ("workspaces", "external_wiki_folder_id", "external_skill_folder_id"),
    ("workspaces", "end_user_wikis_folder_id", "end_user_skills_folder_id"),
    ("end_users", "wiki_folder_id", "skill_folder_id"),
    ("end_users", "share_wiki", "share_skill"),
    ("agents", "curator_wiki", "curator_skill"),
]


def upgrade() -> None:
    for table, old, new in _COLUMNS:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    op.execute(
        "ALTER INDEX idx_folders_one_memory_per_owner RENAME TO idx_folders_one_curated_skill_per_owner"
    )
    op.execute("ALTER INDEX one_curator_per_user_per_wiki RENAME TO one_curator_per_user_per_skill")
    op.execute("ALTER TABLE folders DROP CONSTRAINT folders_protected_is_never_a_skill")
    bind = op.get_bind()
    heavi_scopes = set(
        bind.execute(
            text(
                "SELECT w.scope_user_id FROM workspaces w WHERE w.external_skill_folder_id IS NOT NULL "
                "AND (w.domain='heaviai.com' "
                "OR w.created_by IN (SELECT id FROM users WHERE lower(email)='stash@heaviai.com') "
                "OR w.scope_user_id IN (SELECT id FROM users WHERE lower(email)='stash@heaviai.com'))"
            )
        ).scalars()
    )
    roots = (
        bind.execute(
            text(
                "SELECT f.id,f.owner_user_id,f.name,f.is_curated_skill,eu.id AS end_user_id "
                "FROM folders f LEFT JOIN end_users eu ON eu.skill_folder_id=f.id "
                "WHERE f.is_curated_skill OR eu.id IS NOT NULL "
                "OR f.id IN (SELECT external_skill_folder_id FROM workspaces) "
                "OR (f.is_protected AND f.name LIKE 'Shared wiki archive (%')"
            )
        )
        .mappings()
        .all()
    )
    for root in roots:
        if root["owner_user_id"] in heavi_scopes:
            continue
        name = root["name"]
        archived = name.startswith("Shared wiki archive (")
        if archived:
            name = name.replace("Shared wiki archive", "Shared Skill archive", 1)
        elif root["is_curated_skill"]:
            name = "Learned knowledge"
        elif root["end_user_id"] is None:
            name = "Shared knowledge"
        collision = bind.execute(
            text(
                "SELECT 1 FROM folders WHERE owner_user_id=:owner AND name=:name "
                "AND parent_folder_id IS NOT DISTINCT FROM "
                "(SELECT parent_folder_id FROM folders WHERE id=:id) AND id<>:id"
            ),
            {"owner": root["owner_user_id"], "name": name, "id": root["id"]},
        ).first()
        if collision:
            name = f"{name} ({str(root['id'])[:8]})"
        bind.execute(
            text(
                "UPDATE folders SET name=:name,is_skill=true,skill_created_at=created_at, "
                "agent_enabled=CASE WHEN :archived THEN false ELSE agent_enabled END WHERE id=:id"
            ),
            {"name": name, "id": root["id"], "archived": archived},
        )
        entry = (
            bind.execute(
                text(
                    "SELECT id,name,content_type,content_markdown FROM pages WHERE folder_id=:id AND deleted_at IS NULL "
                    "AND name IN ('SKILL.md','Memory Wiki') "
                    "ORDER BY CASE WHEN name='SKILL.md' THEN 0 ELSE 1 END LIMIT 1"
                ),
                {"id": root["id"]},
            )
            .mappings()
            .first()
        )
        # An HTML index stays intact as a supporting document. SKILL.md is Markdown.
        if entry is not None and entry["content_type"] == "html":
            if entry["name"] == "SKILL.md":
                bind.execute(
                    text("UPDATE pages SET name=:name WHERE id=:id"),
                    {"id": entry["id"], "name": f"Original Skill index ({entry['id']})"},
                )
            entry = None
        # Keep every byte of the old index as supporting text beneath the new metadata.
        body = entry["content_markdown"] if entry is not None else ""
        content = (
            f"---\nname: {json.dumps(name[:64])}\n"
            'description: "Knowledge and guidance learned from this scope\'s activity."\n---\n\n'
            "Consult this Skill for relevant project context, preferences, procedures and facts. "
            "Read its supporting documents before answering or acting. Preserve source citations "
            "and respect each document's scope.\n\n" + body
        )
        params = {
            "id": root["id"],
            "owner": root["owner_user_id"],
            "end_user": root["end_user_id"],
            "content": content,
            "hash": hashlib.sha256(content.encode()).hexdigest(),
        }
        if entry is not None:
            params["page"] = entry["id"]
            bind.execute(
                text(
                    "UPDATE pages SET name='SKILL.md',content_markdown=:content,content_hash=:hash,"
                    "embed_stale=true WHERE id=:page"
                ),
                params,
            )
        else:
            bind.execute(
                text(
                    "INSERT INTO pages (owner_user_id,folder_id,end_user_id,name,content_markdown,"
                    "content_hash,created_by,updated_by) "
                    "VALUES (:owner,:id,:end_user,'SKILL.md',:content,:hash,:owner,:owner)"
                ),
                params,
            )
    op.execute(
        "UPDATE folders SET name='User Skills' WHERE id IN (SELECT end_user_skills_folder_id "
        "FROM workspaces WHERE external_skill_folder_id IN (SELECT id FROM folders WHERE is_skill))"
    )
    op.execute(
        "UPDATE agents SET name=CASE WHEN curator_skill='internal' THEN 'Skills curator' ELSE 'Shared Skills curator' END WHERE is_curator AND user_id IN (SELECT owner_user_id FROM folders WHERE is_curated_skill AND is_skill)"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Skills replace wikis; restore a database backup to reverse this migration."
    )
