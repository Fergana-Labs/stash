"""Collapse multi-tenant workspaces onto a single per-user scope.

This is the foundational step of removing the "workspace" concept. Every user
already has exactly one primary workspace (auto-provisioned at signup); that
primary becomes the user's one-and-only scope. Concretely:

- Re-home every non-primary workspace's content onto its creator's primary
  workspace, then delete the now-empty non-primary workspace.
- Preserve cross-user access (sharing model A): each non-creator membership
  becomes explicit `shares` rows on the workspace's root objects, so people who
  could see shared-workspace content keep seeing it.
- Drop the multi-tenancy machinery: workspace_members, invite tokens.
- Flatten user_pins / user_recents, which were keyed by (user_id, workspace_id);
  one scope per user means the workspace_id is redundant.

After this migration the `workspace_id` columns still exist and still hold a
value (the user's single scope id == their old primary workspace id). They are
renamed to owner columns and the workspaces stub is dropped in a later cleanup
migration. Keeping them here lets every existing query keep working while the
backend is converted to user-scoping.

Revision ID: 0118
Revises: 0117
"""

from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


# Every table carrying a workspace_id that we re-point during consolidation.
# Excludes the workspace_* tables and `workspaces` itself.
_CONTENT_TABLES = (
    "asana_documents",
    "ask_threads",
    "documents",
    "drive_index",
    "embedding_projections",
    "files",
    "folders",
    "github_documents",
    "gmail_index",
    "gong_documents",
    "granola_notes",
    "history_events",
    "jira_documents",
    "knowledge_density_cache",
    "linear_index",
    "notion_index",
    "page_collab_documents",
    "page_edits",
    "pages",
    "security_audit_events",
    "session_folders",
    "session_github_pull_requests",
    "session_linear_tickets",
    "session_titles",
    "sessions",
    "share_invites",
    "share_links",
    "shares",
    "skills",
    "slack_messages",
    "tables",
    "task_records",
    "twitter_posts",
    "user_pins",
    "user_recents",
    "webhooks",
    "workspace_sources",
)


def upgrade() -> None:
    # 1. Defensive: every member-bearing user must have exactly one primary.
    #    If a user somehow has memberships but no primary, promote their oldest.
    op.execute("""
        UPDATE workspace_members wm
        SET is_primary = TRUE
        WHERE wm.is_primary = FALSE
          AND NOT EXISTS (
            SELECT 1 FROM workspace_members p
            WHERE p.user_id = wm.user_id AND p.is_primary
          )
          AND wm.joined_at = (
            SELECT MIN(j.joined_at) FROM workspace_members j WHERE j.user_id = wm.user_id
          )
        """)

    # 2. Map each workspace to the scope it collapses into: its creator's
    #    primary workspace. (For a primary workspace, that's itself.)
    op.execute("""
        CREATE TEMP TABLE ws_target ON COMMIT DROP AS
        SELECT w.id AS old_ws, primary_m.workspace_id AS new_ws
        FROM workspaces w
        JOIN workspace_members primary_m
          ON primary_m.user_id = w.creator_id AND primary_m.is_primary
        """)

    # 3. Preserve access for non-creator members (sharing model A). Each such
    #    membership becomes shares on the workspace's root-level objects; the
    #    permission model cascades folder shares to descendants, so root folders
    #    + root (folderless) pages/files/tables + session folders + skills cover
    #    everything the member could previously see.
    #    owner/editor -> write, viewer -> read.
    op.execute("""
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        SELECT t.new_ws, src.object_type, src.object_id, 'user', wm.user_id,
               CASE WHEN wm.role = 'viewer' THEN 'read' ELSE 'write' END,
               w.creator_id
        FROM workspace_members wm
        JOIN workspaces w ON w.id = wm.workspace_id
        JOIN ws_target t ON t.old_ws = wm.workspace_id
        JOIN LATERAL (
            SELECT 'folder' AS object_type, f.id AS object_id
              FROM folders f WHERE f.workspace_id = wm.workspace_id AND f.parent_folder_id IS NULL
            UNION ALL
            SELECT 'page', p.id FROM pages p
              WHERE p.workspace_id = wm.workspace_id AND p.folder_id IS NULL
            UNION ALL
            SELECT 'file', fi.id FROM files fi
              WHERE fi.workspace_id = wm.workspace_id AND fi.folder_id IS NULL
            UNION ALL
            SELECT 'table', tb.id FROM tables tb
              WHERE tb.workspace_id = wm.workspace_id AND tb.folder_id IS NULL
            UNION ALL
            SELECT 'session_folder', sf.id FROM session_folders sf
              WHERE sf.workspace_id = wm.workspace_id
        ) src ON TRUE
        WHERE wm.user_id <> w.creator_id
          AND NOT EXISTS (
            SELECT 1 FROM shares s
            WHERE s.object_type = src.object_type AND s.object_id = src.object_id
              AND s.principal_type = 'user' AND s.principal_id = wm.user_id
          )
        """)

    # 4. Flatten the (user_id, workspace_id) compound keys BEFORE re-homing, so
    #    collapsing every row to one scope can't collide on the PK. Keep the
    #    most recent row per logical key.
    op.execute("""
        DELETE FROM user_pins a
        USING user_pins b
        WHERE a.user_id = b.user_id AND a.kind = b.kind
          AND (a.updated_at, a.workspace_id) < (b.updated_at, b.workspace_id)
        """)
    op.execute("""
        DELETE FROM user_recents a
        USING user_recents b
        WHERE a.user_id = b.user_id AND a.object_id = b.object_id AND a.kind = b.kind
          AND (a.viewed_at, a.workspace_id) < (b.viewed_at, b.workspace_id)
        """)

    # 4b. Resolve unique-constraint collisions that re-homing would otherwise
    #     trigger. When two workspaces collapse into one scope they can carry
    #     duplicate root folder/page names, more than one default session
    #     folder, and the same external session_id (the same agent session
    #     re-imported in each workspace). Every block keys on the TARGET scope
    #     (ws_target.new_ws) so it sees the post-re-home layout; the row already
    #     living in the target scope wins, and the others are renamed or merged.
    #     The remaining workspace_id-bearing unique keys (embedding_projections,
    #     knowledge_density_cache, webhooks, workspace_sources) carry no
    #     duplicates today, so re-homing them is a no-op.

    # Root folders are unique on (workspace_id, name) where parent_folder_id IS
    # NULL. Rename all but the winner, suffixing with a stable id fragment.
    op.execute("""
        WITH ranked AS (
            SELECT f.id,
                   row_number() OVER (
                       PARTITION BY t.new_ws, f.name
                       ORDER BY (f.workspace_id = t.new_ws) DESC, f.created_at, f.id
                   ) AS rn
            FROM folders f
            JOIN ws_target t ON t.old_ws = f.workspace_id
            WHERE f.parent_folder_id IS NULL
        )
        UPDATE folders f
        SET name = f.name || ' (' || left(f.id::text, 8) || ')'
        FROM ranked
        WHERE ranked.id = f.id AND ranked.rn > 1
        """)

    # Root pages are unique on (workspace_id, name) where folder_id IS NULL.
    op.execute("""
        WITH ranked AS (
            SELECT p.id,
                   row_number() OVER (
                       PARTITION BY t.new_ws, p.name
                       ORDER BY (p.workspace_id = t.new_ws) DESC, p.created_at, p.id
                   ) AS rn
            FROM pages p
            JOIN ws_target t ON t.old_ws = p.workspace_id
            WHERE p.folder_id IS NULL
        )
        UPDATE pages p
        SET name = p.name || ' (' || left(p.id::text, 8) || ')'
        FROM ranked
        WHERE ranked.id = p.id AND ranked.rn > 1
        """)

    # At most one default session folder per scope: keep one, demote the rest.
    op.execute("""
        WITH ranked AS (
            SELECT sf.id,
                   row_number() OVER (
                       PARTITION BY t.new_ws
                       ORDER BY (sf.workspace_id = t.new_ws) DESC, sf.created_at, sf.id
                   ) AS rn
            FROM session_folders sf
            JOIN ws_target t ON t.old_ws = sf.workspace_id
            WHERE sf.is_default
        )
        UPDATE session_folders sf
        SET is_default = FALSE
        FROM ranked
        WHERE ranked.id = sf.id AND ranked.rn > 1
        """)

    # The same external session_id re-imported into several workspaces collides
    # on (workspace_id, session_id). Keep the richest row (most events), move the
    # duplicates' child rows onto it, and drop the rest. history_events have no
    # per-row unique key, so their events fold together under (scope, session_id)
    # when re-homed; the loser's session_titles cascade-delete with its session.
    op.execute("""
        CREATE TEMP TABLE session_dupes ON COMMIT DROP AS
        WITH counted AS (
            SELECT s.id, t.new_ws, s.session_id, s.started_at,
                   (SELECT count(*) FROM history_events he
                    WHERE he.workspace_id = s.workspace_id
                      AND he.session_id = s.session_id) AS events
            FROM sessions s
            JOIN ws_target t ON t.old_ws = s.workspace_id
        ), ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY new_ws, session_id
                       ORDER BY events DESC, started_at, id
                   ) AS keeper_id
            FROM counted
        )
        SELECT id AS loser_id, keeper_id
        FROM ranked
        WHERE id <> keeper_id
        """)
    op.execute("""
        UPDATE session_artifacts a SET session_id = d.keeper_id
        FROM session_dupes d WHERE a.session_id = d.loser_id
        """)
    op.execute("""
        UPDATE session_github_pull_requests p SET session_row_id = d.keeper_id
        FROM session_dupes d WHERE p.session_row_id = d.loser_id
        """)
    op.execute("""
        UPDATE session_linear_tickets l SET session_row_id = d.keeper_id
        FROM session_dupes d WHERE l.session_row_id = d.loser_id
        """)
    op.execute("DELETE FROM sessions s USING session_dupes d WHERE s.id = d.loser_id")

    # The session_titles -> sessions composite FK (workspace_id, session_id) is
    # ON UPDATE NO ACTION, so re-homing the two tables in separate statements
    # transiently dangles it whichever order we pick — and 0119 re-points the
    # same columns again. Drop it now (after the merge above, which relied on its
    # ON DELETE CASCADE) and let 0119 recreate it owner-scoped once both columns
    # have settled.
    op.execute(
        "ALTER TABLE session_titles "
        'DROP CONSTRAINT IF EXISTS "session_titles_workspace_id_session_id_fkey"'
    )

    # 5. Re-home content from every workspace onto its target scope. Some tables
    #    are optional (integration indexes created on first connect, absent in
    #    deployments that never used that integration), so guard each one.
    for table in _CONTENT_TABLES:
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.{table}') IS NULL THEN
                    RETURN;
                END IF;
                UPDATE {table} c
                SET workspace_id = t.new_ws
                FROM ws_target t
                WHERE c.workspace_id = t.old_ws AND c.workspace_id <> t.new_ws;
            END $$;
            """)

    # 6. Delete now-empty non-primary workspaces. Content has been re-homed; the
    #    only rows left pointing at them are workspace_members (about to be
    #    dropped). FK cascades clean up member rows.
    op.execute("""
        DELETE FROM workspaces w
        USING ws_target t
        WHERE w.id = t.old_ws AND t.old_ws <> t.new_ws
        """)

    # 7. Drop the multi-tenancy machinery.
    op.execute("DROP TABLE IF EXISTS workspace_invite_tokens")
    op.execute("DROP TABLE IF EXISTS workspace_members")


def downgrade() -> None:
    raise NotImplementedError("Collapsing to user scope is one-way.")
