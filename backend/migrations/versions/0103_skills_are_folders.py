"""Skills become 1:1 publish records for folders; the bundle model dies.

A skill is now a special folder (one containing a SKILL.md page). The
``skills`` row is just the publish wrapper (slug, access, members, Discover)
pointing at exactly one folder. ``skill_items`` — the arbitrary-item bundle —
is dropped.

Data pass, per existing skill:
- items == exactly one live folder → that folder becomes the skill's folder.
- otherwise → create a root folder named after the skill title and move the
  items in (pages/files/tables reparent; folders reparent; sessions are
  materialized as frozen markdown transcript pages — sessions cannot live in
  folders).
- folders lacking a SKILL.md get a template page so they read as skills.

The ``shared_in_skill_id`` page/file metadata key dies with the bundle model
(skill-owned pages now simply live in the folder), so the three pages partial
indexes from 0102 lose that predicate.

Like 0075/0100 this is a data migration: transcript materialization and item
moves are irreversible; ``downgrade()`` restores the schema and a semantically
close one-folder-item bundle per skill.

Revision ID: 0103
Revises: 0102
"""

import hashlib
import json
import uuid

from alembic import op
from sqlalchemy import text

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

_EVENT_LIMIT = 2000
_EVENT_CONTENT_CAP = 20_000


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _render_session_markdown(bind, workspace_id, session_row) -> str:
    """Frozen transcript, mirroring the old inline session rendering."""
    files_touched = session_row.files_touched or []
    if isinstance(files_touched, str):
        files_touched = json.loads(files_touched)
    lines = [
        f"# Session {session_row.session_id}",
        f"Agent: {session_row.agent_name or 'agent'}",
    ]
    if files_touched:
        lines.append("## Files Touched")
        lines.extend(f"- {path}" for path in files_touched)
    events = bind.execute(
        text(
            "SELECT agent_name, event_type, content FROM history_events "
            "WHERE workspace_id = :ws AND session_id = :sid "
            "ORDER BY created_at LIMIT :lim"
        ),
        {"ws": workspace_id, "sid": session_row.session_id, "lim": _EVENT_LIMIT},
    ).fetchall()
    if events:
        lines.append("## Events")
        for event in events:
            content = event.content or ""
            if not content:
                continue
            if len(content) > _EVENT_CONTENT_CAP:
                content = content[:_EVENT_CONTENT_CAP] + "\n\n[truncated]"
            lines.append(
                f"### {event.event_type or 'event'} ({event.agent_name or 'agent'})\n\n{content}"
            )
    return "\n\n".join(lines)


def _unique_name(bind, table, workspace_id, folder_id, base_name, exclude_id=None):
    """Dedupe a page/file name within (workspace, folder) with ' (N)' suffixes."""
    name = base_name
    n = 2
    # NB: ":skip::uuid" is unusable here — SQLAlchemy's :param parser trips
    # over the ::cast and leaves a literal ":" in the SQL. Branch instead.
    folder_clause = "folder_id = :fid" if folder_id else "folder_id IS NULL"
    skip_clause = "AND id != :skip " if exclude_id else ""
    params = {"ws": workspace_id, "name": name}
    if folder_id:
        params["fid"] = folder_id
    if exclude_id:
        params["skip"] = exclude_id
    while True:
        params["name"] = name
        hit = bind.execute(
            text(
                f"SELECT 1 FROM {table} WHERE workspace_id = :ws AND {folder_clause} "
                f"AND name = :name AND deleted_at IS NULL {skip_clause}LIMIT 1"
            ),
            params,
        ).fetchone()
        if not hit:
            return name
        name = f"{base_name} ({n})"
        n += 1


def _unique_root_folder_name(bind, workspace_id, base_name):
    name = base_name or "Skill"
    n = 2
    while True:
        hit = bind.execute(
            text(
                "SELECT 1 FROM folders WHERE workspace_id = :ws "
                "AND parent_folder_id IS NULL AND name = :name LIMIT 1"
            ),
            {"ws": workspace_id, "name": name},
        ).fetchone()
        if not hit:
            return name
        name = f"{base_name} ({n})"
        n += 1


def _insert_page(bind, workspace_id, folder_id, owner_id, name, content):
    name = _unique_name(bind, "pages", workspace_id, folder_id, name)
    bind.execute(
        text(
            "INSERT INTO pages (id, workspace_id, folder_id, name, content_markdown, "
            "content_html, content_type, html_layout, content_hash, metadata, "
            "created_by, updated_by) "
            "VALUES (:id, :ws, :fid, :name, :md, '', 'markdown', 'responsive', "
            ":hash, '{}'::jsonb, :uid, :uid)"
        ),
        {
            "id": str(uuid.uuid4()),
            "ws": workspace_id,
            "fid": folder_id,
            "name": name,
            "md": content,
            "hash": _content_hash(content),
            "uid": owner_id,
        },
    )


def _skill_md_template(title: str, description: str) -> str:
    return f"---\nname: {title}\ndescription: {description or ''}\n---\n\n# {title}\n"


def _adopt_folder(bind, skill) -> str:
    """Resolve the folder a skill row should point at, moving items as needed."""
    items = bind.execute(
        text(
            "SELECT object_type, object_id, position, label_override FROM skill_items "
            "WHERE skill_id = :sid ORDER BY position, object_type, object_id"
        ),
        {"sid": skill.id},
    ).fetchall()

    if len(items) == 1 and items[0].object_type == "folder":
        folder = bind.execute(
            text("SELECT id FROM folders WHERE id = :fid AND workspace_id = :ws"),
            {"fid": items[0].object_id, "ws": skill.workspace_id},
        ).fetchone()
        if folder:
            return folder.id

    folder_name = _unique_root_folder_name(bind, skill.workspace_id, skill.title)
    folder_id = str(uuid.uuid4())
    bind.execute(
        text(
            "INSERT INTO folders (id, workspace_id, parent_folder_id, name, created_by) "
            "VALUES (:id, :ws, NULL, :name, :uid)"
        ),
        {"id": folder_id, "ws": skill.workspace_id, "name": folder_name, "uid": skill.owner_id},
    )

    for item in items:
        if item.object_type == "folder":
            bind.execute(
                text(
                    "UPDATE folders SET parent_folder_id = :fid "
                    "WHERE id = :oid AND workspace_id = :ws AND id != :fid"
                ),
                {"fid": folder_id, "oid": item.object_id, "ws": skill.workspace_id},
            )
        elif item.object_type in ("page", "file", "table"):
            table = {"page": "pages", "file": "files", "table": "tables"}[item.object_type]
            bind.execute(
                text(f"UPDATE {table} SET folder_id = :fid WHERE id = :oid AND workspace_id = :ws"),
                {"fid": folder_id, "oid": item.object_id, "ws": skill.workspace_id},
            )
        elif item.object_type == "session":
            session_row = bind.execute(
                text(
                    "SELECT id, session_id, agent_name, files_touched FROM sessions "
                    "WHERE id = :oid AND deleted_at IS NULL"
                ),
                {"oid": item.object_id},
            ).fetchone()
            if session_row:
                content = _render_session_markdown(bind, skill.workspace_id, session_row)
                page_name = (item.label_override or f"Session {session_row.session_id}") + ".md"
                _insert_page(
                    bind, skill.workspace_id, folder_id, skill.owner_id, page_name, content
                )

    # Skill-owned shared pages whose item row was deleted still carry the
    # ownership marker — sweep them into the folder too.
    bind.execute(
        text(
            "UPDATE pages SET folder_id = :fid "
            "WHERE workspace_id = :ws AND metadata->>'shared_in_skill_id' = :sid "
            "AND folder_id IS DISTINCT FROM :fid"
        ),
        {"fid": folder_id, "ws": skill.workspace_id, "sid": str(skill.id)},
    )
    bind.execute(
        text(
            "UPDATE files SET folder_id = :fid "
            "WHERE workspace_id = :ws AND metadata->>'shared_in_skill_id' = :sid "
            "AND folder_id IS DISTINCT FROM :fid"
        ),
        {"fid": folder_id, "ws": skill.workspace_id, "sid": str(skill.id)},
    )
    return folder_id


def _recreate_pages_partial_indexes(with_skill_marker: bool) -> None:
    marker = " AND COALESCE(metadata->>'shared_in_skill_id', '') = ''" if with_skill_marker else ""
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute(f"""
        CREATE UNIQUE INDEX idx_pages_unique_in_folder
        ON pages (workspace_id, folder_id, name)
        WHERE folder_id IS NOT NULL{marker}
        """)
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute(f"""
        CREATE UNIQUE INDEX idx_pages_unique_at_root
        ON pages (workspace_id, name)
        WHERE folder_id IS NULL{marker}
        """)
    op.execute("DROP INDEX IF EXISTS idx_pages_workspace_active_folder_name")
    op.execute(f"""
        CREATE INDEX idx_pages_workspace_active_folder_name
        ON pages (workspace_id, folder_id, name)
        WHERE deleted_at IS NULL{marker}
        """)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        "ALTER TABLE skills ADD COLUMN folder_id UUID REFERENCES folders(id) ON DELETE CASCADE"
    )

    skills = bind.execute(
        text(
            "SELECT id, workspace_id, owner_id, title, description FROM skills ORDER BY created_at"
        )
    ).fetchall()
    claimed: set = set()
    for skill in skills:
        folder_id = _adopt_folder(bind, skill)
        if folder_id in claimed:
            # folder_id is going UNIQUE; a folder bundled into two skills keeps
            # the first and the later skill gets a fresh wrapper folder.
            wrapper_name = _unique_root_folder_name(bind, skill.workspace_id, skill.title)
            wrapper_id = str(uuid.uuid4())
            bind.execute(
                text(
                    "INSERT INTO folders (id, workspace_id, parent_folder_id, name, created_by) "
                    "VALUES (:id, :ws, NULL, :name, :uid)"
                ),
                {
                    "id": wrapper_id,
                    "ws": skill.workspace_id,
                    "name": wrapper_name,
                    "uid": skill.owner_id,
                },
            )
            folder_id = wrapper_id
        claimed.add(folder_id)
        bind.execute(
            text("UPDATE skills SET folder_id = :fid WHERE id = :sid"),
            {"fid": folder_id, "sid": skill.id},
        )

        has_skill_md = bind.execute(
            text(
                "SELECT 1 FROM pages WHERE folder_id = :fid AND name = 'SKILL.md' "
                "AND deleted_at IS NULL LIMIT 1"
            ),
            {"fid": folder_id},
        ).fetchone()
        if not has_skill_md:
            _insert_page(
                bind,
                skill.workspace_id,
                folder_id,
                skill.owner_id,
                "SKILL.md",
                _skill_md_template(skill.title, skill.description or ""),
            )

    # The ownership marker dies. Names were excluded from the unique partial
    # indexes while marked, so dedupe before stripping.
    for table in ("pages", "files"):
        marked = bind.execute(
            text(
                f"SELECT id, workspace_id, folder_id, name FROM {table} "
                "WHERE metadata ? 'shared_in_skill_id' AND deleted_at IS NULL"
            )
        ).fetchall()
        for row in marked:
            bind.execute(
                text(
                    f"UPDATE {table} SET metadata = metadata - 'shared_in_skill_id' WHERE id = :id"
                ),
                {"id": row.id},
            )
            fresh = _unique_name(
                bind, table, row.workspace_id, row.folder_id, row.name, exclude_id=row.id
            )
            if fresh != row.name:
                bind.execute(
                    text(f"UPDATE {table} SET name = :name WHERE id = :id"),
                    {"name": fresh, "id": row.id},
                )
        bind.execute(
            text(
                f"UPDATE {table} SET metadata = metadata - 'shared_in_skill_id' WHERE metadata ? 'shared_in_skill_id'"
            )
        )

    _recreate_pages_partial_indexes(with_skill_marker=False)

    op.execute("ALTER TABLE skills ALTER COLUMN folder_id SET NOT NULL")
    op.execute("ALTER TABLE skills ADD CONSTRAINT skills_folder_id_key UNIQUE (folder_id)")
    op.execute("DROP TABLE skill_items")
    op.execute("DROP INDEX IF EXISTS idx_skills_one_fork_per_workspace")
    op.execute("ALTER TABLE skills DROP COLUMN forked_from_skill_id")

    op.execute(
        "UPDATE user_recents SET object_id = skills.folder_id::text, kind = 'folder' "
        "FROM skills WHERE user_recents.kind = 'skill' "
        "AND user_recents.object_id = skills.id::text"
    )


def downgrade() -> None:
    # Schema-honest, data-lossy: moved items and transcript pages stay put.
    op.execute("ALTER TABLE skills ADD COLUMN forked_from_skill_id UUID REFERENCES skills(id)")
    op.execute("""
        CREATE UNIQUE INDEX idx_skills_one_fork_per_workspace
        ON skills (workspace_id, forked_from_skill_id)
        WHERE forked_from_skill_id IS NOT NULL
        """)
    op.execute("""
        CREATE TABLE skill_items (
            skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            object_type VARCHAR(16) NOT NULL
                CONSTRAINT skill_items_object_type_check
                CHECK (object_type IN ('folder', 'page', 'table', 'file', 'session')),
            object_id UUID NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            label_override TEXT,
            CONSTRAINT skill_items_pkey PRIMARY KEY (skill_id, object_type, object_id)
        )
        """)
    op.execute("CREATE INDEX idx_skill_items_position ON skill_items (skill_id, position)")
    op.execute(
        "INSERT INTO skill_items (skill_id, object_type, object_id, position) "
        "SELECT id, 'folder', folder_id, 0 FROM skills"
    )
    op.execute("ALTER TABLE skills DROP CONSTRAINT skills_folder_id_key")
    op.execute("ALTER TABLE skills DROP COLUMN folder_id")
    _recreate_pages_partial_indexes(with_skill_marker=True)
