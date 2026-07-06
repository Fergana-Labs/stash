"""Unified public sharing: 'public' is a share principal, not a bespoke flag.

One sharing system for every resource. A `shares` row with
principal_type='public' (principal_id NULL, read-only) makes an object — and,
via the usual cascade, its contents — readable by anyone, including anonymous
viewers. This replaces the two bespoke public mechanisms:

- Skill publishing: a `skills` row's existence used to BE the public grant.
  Now the row is pure classification + metadata (a folder is a skill iff it
  has a `skills` row — no more SKILL.md sniffing), and public readability is a
  public share on the folder. Every existing skill folder gets a record;
  every previously-published skill gets a public share.
- `session_folders.public_permission` (and its never-surfaced `discoverable`):
  folders that were public get a public share; both columns are dropped.

Also adds `pages.snapshot_key`: snapshot pages (materialized sessions,
source-doc snapshots) record their origin so a re-snapshot replaces the page
in place instead of duplicating it.

Revision ID: 0135
Revises: 0134
"""

import re
import secrets

from alembic import op
from sqlalchemy import text

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:64] or "skill"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


def upgrade() -> None:
    bind = op.get_bind()

    # Public shares: principal_id is NULL, permission is read-only, one per object.
    op.execute("ALTER TABLE shares ALTER COLUMN principal_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE shares ADD CONSTRAINT shares_public_shape CHECK ("
        "  (principal_type = 'public' AND principal_id IS NULL AND permission = 'read')"
        "  OR (principal_type <> 'public' AND principal_id IS NOT NULL)"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX shares_public_unique ON shares (object_type, object_id) "
        "WHERE principal_type = 'public'"
    )

    # Published skills were public — mint their public share before the record
    # backfill below makes record-existence meaningless.
    op.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "                    principal_id, permission, created_by) "
        "SELECT owner_user_id, 'folder', folder_id, 'public', NULL, 'read', owner_id "
        "FROM skills"
    )

    # Every SKILL.md folder becomes an explicitly classified skill.
    unrecorded = bind.execute(
        text(
            "SELECT f.id, f.owner_user_id, f.name FROM folders f "
            "WHERE EXISTS (SELECT 1 FROM pages p WHERE p.folder_id = f.id "
            "              AND p.name = 'SKILL.md' AND p.deleted_at IS NULL) "
            "AND NOT EXISTS (SELECT 1 FROM skills s WHERE s.folder_id = f.id)"
        )
    ).fetchall()
    for folder in unrecorded:
        bind.execute(
            text(
                "INSERT INTO skills (owner_user_id, folder_id, slug, title, description, "
                "                    owner_id, discoverable) "
                "VALUES (:owner_user_id, :folder_id, :slug, :title, '', :owner_id, false)"
            ),
            {
                "owner_user_id": folder.owner_user_id,
                "folder_id": folder.id,
                "slug": _slugify(folder.name),
                "title": folder.name,
                "owner_id": folder.owner_user_id,
            },
        )

    # Public session folders move onto the same system, then the bespoke
    # columns die.
    op.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "                    principal_id, permission, created_by) "
        "SELECT owner_user_id, 'session_folder', id, 'public', NULL, 'read', owner_user_id "
        "FROM session_folders WHERE public_permission <> 'none'"
    )
    op.execute("ALTER TABLE session_folders DROP COLUMN public_permission")
    op.execute("ALTER TABLE session_folders DROP COLUMN discoverable")

    # Snapshot origin: one live snapshot per origin per folder.
    op.execute("ALTER TABLE pages ADD COLUMN snapshot_key text")
    op.execute(
        "CREATE UNIQUE INDEX pages_snapshot_key_unique ON pages (folder_id, snapshot_key) "
        "WHERE snapshot_key IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS pages_snapshot_key_unique")
    op.execute("ALTER TABLE pages DROP COLUMN snapshot_key")
    op.execute("ALTER TABLE session_folders ADD COLUMN discoverable boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE session_folders ADD COLUMN public_permission varchar(16) "
        "NOT NULL DEFAULT 'none'"
    )
    op.execute(
        "UPDATE session_folders SET public_permission = 'read' "
        "WHERE EXISTS (SELECT 1 FROM shares s WHERE s.object_type = 'session_folder' "
        "              AND s.object_id = session_folders.id AND s.principal_type = 'public')"
    )
    op.execute(
        "DELETE FROM skills WHERE NOT EXISTS ("
        "  SELECT 1 FROM shares s WHERE s.object_type = 'folder' "
        "  AND s.object_id = skills.folder_id AND s.principal_type = 'public')"
    )
    op.execute("DELETE FROM shares WHERE principal_type = 'public'")
    op.execute("DROP INDEX IF EXISTS shares_public_unique")
    op.execute("ALTER TABLE shares DROP CONSTRAINT shares_public_shape")
    op.execute("ALTER TABLE shares ALTER COLUMN principal_id SET NOT NULL")
