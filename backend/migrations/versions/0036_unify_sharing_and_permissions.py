"""Unify naming, sharing, and permissions into one model.

Single PR that collapses the remaining duplication from the May 10
audit:

- **stash = workspace** in both code and product. The thing the user
  sees as their top-level container.
- **session_shares are the renamed `stashes` table.** Files-touched and
  AI summaries live on a new lightweight `sessions` table; the share
  link itself lives in `share_links` with a polymorphic target.
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
    # ──────────────────────────────────────────────────────────────────
    # 1. sessions — first-class session-metadata table
    # ──────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            cwd TEXT,
            summary TEXT,
            status TEXT NOT NULL DEFAULT 'live'
                CHECK (status IN ('live', 'summarizing', 'ready', 'failed')),
            files_touched JSONB NOT NULL DEFAULT '[]',
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            UNIQUE (workspace_id, session_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_id)")

    # Backfill from history_events — one sessions row per (workspace_id, session_id)
    # that has any events. Idempotent via ON CONFLICT.
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
    op.execute("""
        INSERT INTO sessions (
            workspace_id, session_id, agent_name, cwd, summary, status,
            files_touched, started_at, finished_at, created_by
        )
        SELECT st.workspace_id,
               st.session_id,
               st.agent_name,
               st.cwd,
               st.summary,
               CASE
                   WHEN st.status IN ('live','summarizing','ready','failed') THEN st.status
                   ELSE 'live'
               END,
               st.files_touched,
               st.created_at,
               st.updated_at,
               st.created_by
        FROM stashes st
        ON CONFLICT (workspace_id, session_id) DO NOTHING
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_workspace_session "
        "ON history_events(workspace_id, session_id)"
    )
    op.execute(
        "ALTER TABLE history_events "
        "DROP CONSTRAINT IF EXISTS history_events_workspace_session_fk"
    )
    op.execute(
        "ALTER TABLE history_events "
        "ADD CONSTRAINT history_events_workspace_session_fk "
        "FOREIGN KEY (workspace_id, session_id) "
        "REFERENCES sessions(workspace_id, session_id)"
    )

    # Copy session-level metadata from any existing stashes rows.
    op.execute("""
        UPDATE sessions s
        SET summary = COALESCE(s.summary, st.summary),
            status = CASE
                WHEN st.status IN ('live','summarizing','ready','failed') THEN st.status
                ELSE s.status
            END,
            files_touched = CASE
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
    op.execute("ALTER TABLE IF EXISTS stash_artifacts RENAME TO session_artifacts")
    op.execute(
        "ALTER TABLE session_artifacts "
        "ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(id) ON DELETE CASCADE"
    )
    # Backfill via the join through the still-living stashes table.
    op.execute("""
        UPDATE session_artifacts sa
        SET session_id = s.id
        FROM stashes st
        JOIN sessions s
            ON s.workspace_id = st.workspace_id AND s.session_id = st.session_id
        WHERE sa.stash_id = st.id AND sa.session_id IS NULL
    """)
    op.execute("ALTER TABLE session_artifacts DROP COLUMN IF EXISTS stash_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_artifacts_session "
        "ON session_artifacts(session_id)"
    )

    # ──────────────────────────────────────────────────────────────────
    # 3. share_links — extend with polymorphic target + slug
    # ──────────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS target_type TEXT")
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS target_id UUID")
    op.execute("ALTER TABLE share_links ADD COLUMN IF NOT EXISTS slug TEXT")

    # Existing share_links rows are workspace-targeted (that's all they could
    # have been before this PR).
    op.execute(
        "UPDATE share_links SET target_type = 'workspace', target_id = workspace_id "
        "WHERE target_type IS NULL"
    )

    # Collapse the old permission enum (view, comment, edit-request) to (view, edit).
    op.execute(
        "UPDATE share_links SET permission = 'view' WHERE permission IN ('comment', 'edit-request')"
    )
    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_permission_check")
    op.execute(
        "ALTER TABLE share_links ADD CONSTRAINT share_links_permission_check "
        "CHECK (permission IN ('view', 'edit'))"
    )

    # target_type / target_id constraints.
    op.execute("ALTER TABLE share_links DROP CONSTRAINT IF EXISTS share_links_target_type_check")
    op.execute(
        "ALTER TABLE share_links ADD CONSTRAINT share_links_target_type_check "
        "CHECK (target_type IN ('workspace', 'session', 'page', 'folder', 'file'))"
    )
    op.execute("ALTER TABLE share_links ALTER COLUMN target_type SET NOT NULL")
    op.execute("ALTER TABLE share_links ALTER COLUMN target_id SET NOT NULL")

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

    # Now safe to drop the table.
    op.execute("DROP TABLE IF EXISTS stashes CASCADE")

    # ──────────────────────────────────────────────────────────────────
    # 5. workspace_members.role → owner/editor/viewer
    # ──────────────────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_role_check"
    )
    op.execute("UPDATE workspace_members SET role = 'owner' WHERE role IN ('admin', 'owner')")
    op.execute(
        "UPDATE workspace_members SET role = 'editor' "
        "WHERE role IS NULL OR role NOT IN ('owner', 'editor', 'viewer')"
    )
    op.execute(
        "ALTER TABLE workspace_members ADD CONSTRAINT workspace_members_role_check "
        "CHECK (role IN ('owner', 'editor', 'viewer'))"
    )

    # ──────────────────────────────────────────────────────────────────
    # 6. One-time defensive backfill of object_permissions from the
    #    legacy visibility columns, then drop those columns.
    # ──────────────────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'workspace', id, 'public' FROM workspaces WHERE is_public = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'view', id, 'public' FROM views WHERE is_public = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'page', id, 'public' FROM pages WHERE public_in_share = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)
    op.execute("""
        INSERT INTO object_permissions (object_type, object_id, visibility)
        SELECT 'file', id, 'public' FROM files WHERE public_in_share = true
        ON CONFLICT (object_type, object_id) DO UPDATE SET visibility = 'public'
    """)

    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS is_public")
    op.execute("ALTER TABLE views DROP COLUMN IF EXISTS is_public")
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS public_in_share")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS public_in_share")


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
            summary TEXT,
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

    op.execute(
        "ALTER TABLE history_events "
        "DROP CONSTRAINT IF EXISTS history_events_workspace_session_fk"
    )
    op.execute("DROP INDEX IF EXISTS idx_history_events_workspace_session")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
