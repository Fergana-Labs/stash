"""Unify naming, sharing, and permissions into one model.

Single PR that collapses the remaining duplication from the May 10
audit:

- **stash = workspace** in both code and product. The thing the user
  sees as their top-level container.
- **session_shares are the renamed `stashes` table.** Files-touched metadata
  lives on a new lightweight `sessions` table; the share link itself lives in
  `share_links` with a polymorphic target.
- **session_artifacts replaces stash_artifacts.**
- **One visibility table.** Drop `workspaces.is_public`, `views.is_public`,
  `pages.public_in_share`, `files.public_in_share`; everything goes
  through `object_permissions`.
- **Three roles.** `workspace_members.role` becomes
  CHECK (role IN ('owner','editor','viewer')).

Forward-only. Downgrade is best-effort: it can't re-invent the link
between a now-deleted `stashes` row and the `share_links` row that
replaced it.

Revision ID: 0036
Revises: 0035
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import logging

    log = logging.getLogger("alembic.migration.0036")

    def step(msg: str) -> None:
        log.info("0036 step: %s", msg)

    # ──────────────────────────────────────────────────────────────────
    # 1. sessions — first-class session-metadata table
    # ──────────────────────────────────────────────────────────────────
    step("1a. CREATE TABLE sessions")
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            cwd TEXT,
            files_touched JSONB NOT NULL DEFAULT '[]',
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            UNIQUE (workspace_id, session_id)
        )
    """)
    step("1b. idx_sessions_workspace")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_id)")

    step("1c. backfill sessions from history_events")
    # Backfill from history_events — one sessions row per (workspace_id, session_id)
    # that has any events. Idempotent via ON CONFLICT.
    #
    # NOTE: Postgres has no built-in MIN(uuid) aggregate, so we pull the
    # earliest event's created_by via ARRAY_AGG ordered by created_at.
    op.execute("""
        INSERT INTO sessions (workspace_id, session_id, agent_name, started_at, finished_at, created_by)
        SELECT workspace_id, session_id,
               COALESCE(MAX(agent_name), ''),
               MIN(created_at),
               MAX(created_at),
               (ARRAY_AGG(created_by ORDER BY created_at) FILTER (WHERE created_by IS NOT NULL))[1]
        FROM history_events
        WHERE workspace_id IS NOT NULL AND session_id IS NOT NULL
        GROUP BY workspace_id, session_id
        ON CONFLICT (workspace_id, session_id) DO NOTHING
    """)

    step("1d. copy session metadata from stashes")
    # Copy session-level metadata from any existing stashes rows.
    op.execute("""
        UPDATE sessions s
        SET files_touched = CASE
                WHEN s.files_touched = '[]'::jsonb THEN st.files_touched
                ELSE s.files_touched
            END,
            cwd = COALESCE(s.cwd, st.cwd),
            created_by = COALESCE(s.created_by, st.created_by)
        FROM stashes st
        WHERE s.workspace_id = st.workspace_id AND s.session_id = st.session_id
    """)

    # ──────────────────────────────────────────────────────────────────
    # 2. session_artifacts — renamed from stash_artifacts, FK to sessions
    # ──────────────────────────────────────────────────────────────────
    step("2a. RENAME stash_artifacts -> session_artifacts")
    op.execute("ALTER TABLE IF EXISTS stash_artifacts RENAME TO session_artifacts")
    step("2b. ADD COLUMN session_artifacts.session_id")
    op.execute(
        "ALTER TABLE session_artifacts "
        "ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(id) ON DELETE CASCADE"
    )
    step("2c. backfill session_artifacts.session_id from stashes")
    # Backfill via the join through the still-living stashes table.
    op.execute("""
        UPDATE session_artifacts sa
        SET session_id = s.id
        FROM stashes st
        JOIN sessions s
            ON s.workspace_id = st.workspace_id AND s.session_id = st.session_id
        WHERE sa.stash_id = st.id AND sa.session_id IS NULL
    """)
    step("2d. DROP session_artifacts.stash_id")
    op.execute("ALTER TABLE session_artifacts DROP COLUMN IF EXISTS stash_id")
    step("2e. idx_session_artifacts_session")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_artifacts_session "
        "ON session_artifacts(session_id)"
    )

    # ──────────────────────────────────────────────────────────────────
    # 3. share_links — extend with polymorphic target + slug
    # ──────────────────────────────────────────────────────────────────
    step("3a. ADD COLUMN share_links.target_type / target_id / slug")
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS target_type TEXT")
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS target_id UUID")
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS slug TEXT")

    step("3b. backfill share_links target_type/id = workspace")
    op.execute(
        "UPDATE share_links SET target_type = 'workspace', target_id = workspace_id "
        "WHERE target_type IS NULL"
    )

    step("3c. collapse permission enum to (view, edit)")
    op.execute(
        "UPDATE share_links SET permission = 'view' WHERE permission IN ('comment', 'edit-request')"
    )
    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_permission_check")
    op.execute(
        "ALTER TABLE share_links ADD CONSTRAINT share_links_permission_check "
        "CHECK (permission IN ('view', 'edit'))"
    )

    step("3d. target_type CHECK + NOT NULL")
    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_target_type_check")
    op.execute(
        "ALTER TABLE share_links ADD CONSTRAINT share_links_target_type_check "
        "CHECK (target_type IN ('workspace', 'session', 'page', 'folder', 'file'))"
    )
    op.execute("ALTER TABLE share_links ALTER COLUMN target_type SET NOT NULL")
    op.execute("ALTER TABLE share_links ALTER COLUMN target_id SET NOT NULL")

    step("3e. share_links indexes")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_share_links_slug "
        "ON share_links(slug) WHERE slug IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_share_links_target "
        "ON share_links(target_type, target_id)"
    )

    # ──────────────────────────────────────────────────────────────────
    # 4. Migrate every `stashes` row into a `share_links` row.
    # ──────────────────────────────────────────────────────────────────
    step("4a. INSERT INTO share_links FROM stashes JOIN sessions")
    op.execute("""
        INSERT INTO share_links (
            token, workspace_id, created_by, created_at,
            permission, view_count, target_type, target_id, slug
        )
        SELECT
            'b-' || st.slug,
            st.workspace_id,
            st.created_by,
            st.created_at,
            'view',
            0,
            'session',
            s.id,
            st.slug
        FROM stashes st
        JOIN sessions s
            ON s.workspace_id = st.workspace_id AND s.session_id = st.session_id
        ON CONFLICT (token) DO NOTHING
    """)

    step("4b. DROP TABLE stashes CASCADE")
    op.execute("DROP TABLE IF EXISTS stashes CASCADE")

    # ──────────────────────────────────────────────────────────────────
    # 5. workspace_members.role → owner/editor/viewer
    # ──────────────────────────────────────────────────────────────────
    step("5a. DROP workspace_members role check")
    op.execute(
        "ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_role_check"
    )
    step("5b. UPDATE roles admin->owner")
    op.execute("UPDATE workspace_members SET role = 'owner' WHERE role IN ('admin', 'owner')")
    step("5c. UPDATE roles other->editor")
    op.execute(
        "UPDATE workspace_members SET role = 'editor' "
        "WHERE role IS NULL OR role NOT IN ('owner', 'editor', 'viewer')"
    )
    step("5d. ADD workspace_members role check (owner/editor/viewer)")
    op.execute(
        "ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_role_check "
        "CHECK (role IN ('owner', 'editor', 'viewer'))"
    )

    # ──────────────────────────────────────────────────────────────────
    # 6. One-time defensive backfill of object_permissions from the
    #    legacy visibility columns, then drop those columns.
    # ──────────────────────────────────────────────────────────────────
    step("6a. backfill object_permissions from workspaces.is_public")
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'workspace', id, 'public' FROM workspaces WHERE is_public = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    step("6b. backfill object_permissions from views.is_public")
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'view', id, 'public' FROM views WHERE is_public = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    step("6c. backfill object_permissions from pages.public_in_share")
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'page', id, 'public' FROM pages WHERE public_in_share = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    step("6d. backfill object_permissions from files.public_in_share")
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'file', id, 'public' FROM files WHERE public_in_share = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)

    step("6e. DROP workspaces.is_public")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS is_public")
    step("6f. DROP views.is_public")
    op.execute("ALTER TABLE views DROP COLUMN IF EXISTS is_public")
    step("6g. DROP pages.public_in_share")
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS public_in_share")
    step("6h. DROP files.public_in_share")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS public_in_share")
    step("done")


def downgrade() -> None:
    # Schema-only restore. The blob and metadata mappings can't be
    # round-tripped — this just gets the columns back so the old code
    # boots.
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE views ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS public_in_share BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS public_in_share BOOLEAN NOT NULL DEFAULT FALSE"
    )

    op.execute(
        "ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_role_check"
    )
    op.execute(
        "ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_role_check "
        "CHECK (role IN ('owner', 'admin', 'member'))"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS stashes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            agent_name TEXT NOT NULL DEFAULT '',
            cwd TEXT,
            status TEXT NOT NULL DEFAULT 'live',
            files_touched JSONB NOT NULL DEFAULT '[]',
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("ALTER TABLE session_artifacts ADD COLUMN IF NOT EXISTS stash_id UUID")
    op.execute("ALTER TABLE session_artifacts DROP COLUMN IF EXISTS session_id")
    op.execute("ALTER TABLE IF EXISTS session_artifacts RENAME TO stash_artifacts")

    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_permission_check")
    op.execute(
        "ALTER TABLE share_links ADD CONSTRAINT share_links_permission_check "
        "CHECK (permission IN ('view', 'comment', 'edit-request'))"
    )
    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_target_type_check")
    op.execute("DROP INDEX IF EXISTS idx_share_links_slug")
    op.execute("DROP INDEX IF EXISTS idx_share_links_target")
    op.execute("ALTER TABLE share_links DROP COLUMN IF EXISTS slug")
    op.execute("ALTER TABLE share_links DROP COLUMN IF EXISTS target_id")
    op.execute("ALTER TABLE share_links DROP COLUMN IF EXISTS target_type")

    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
