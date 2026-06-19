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
    op.execute(
        """
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
        """
    )

    # 2. Map each workspace to the scope it collapses into: its creator's
    #    primary workspace. (For a primary workspace, that's itself.)
    op.execute(
        """
        CREATE TEMP TABLE ws_target ON COMMIT DROP AS
        SELECT w.id AS old_ws, primary_m.workspace_id AS new_ws
        FROM workspaces w
        JOIN workspace_members primary_m
          ON primary_m.user_id = w.creator_id AND primary_m.is_primary
        """
    )

    # 3. Preserve access for non-creator members (sharing model A). Each such
    #    membership becomes shares on the workspace's root-level objects; the
    #    permission model cascades folder shares to descendants, so root folders
    #    + root (folderless) pages/files/tables + session folders + skills cover
    #    everything the member could previously see.
    #    owner/editor -> write, viewer -> read.
    op.execute(
        """
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
            UNION ALL
            SELECT 'skill', sk.id FROM skills sk WHERE sk.workspace_id = wm.workspace_id
        ) src ON TRUE
        WHERE wm.user_id <> w.creator_id
          AND NOT EXISTS (
            SELECT 1 FROM shares s
            WHERE s.object_type = src.object_type AND s.object_id = src.object_id
              AND s.principal_type = 'user' AND s.principal_id = wm.user_id
          )
        """
    )

    # 4. Flatten the (user_id, workspace_id) compound keys BEFORE re-homing, so
    #    collapsing every row to one scope can't collide on the PK. Keep the
    #    most recent row per logical key.
    op.execute(
        """
        DELETE FROM user_pins a
        USING user_pins b
        WHERE a.user_id = b.user_id AND a.kind = b.kind
          AND (a.updated_at, a.workspace_id) < (b.updated_at, b.workspace_id)
        """
    )
    op.execute(
        """
        DELETE FROM user_recents a
        USING user_recents b
        WHERE a.user_id = b.user_id AND a.object_id = b.object_id AND a.kind = b.kind
          AND (a.viewed_at, a.workspace_id) < (b.viewed_at, b.workspace_id)
        """
    )

    # 5. Re-home content from every workspace onto its target scope.
    for table in _CONTENT_TABLES:
        op.execute(
            f"""
            UPDATE {table} c
            SET workspace_id = t.new_ws
            FROM ws_target t
            WHERE c.workspace_id = t.old_ws AND c.workspace_id <> t.new_ws
            """
        )

    # 6. Delete now-empty non-primary workspaces. Content has been re-homed; the
    #    only rows left pointing at them are workspace_members (about to be
    #    dropped). FK cascades clean up member rows.
    op.execute(
        """
        DELETE FROM workspaces w
        USING ws_target t
        WHERE w.id = t.old_ws AND t.old_ws <> t.new_ws
        """
    )

    # 7. Drop the multi-tenancy machinery.
    op.execute("DROP TABLE IF EXISTS workspace_invite_tokens")
    op.execute("DROP TABLE IF EXISTS workspace_members")


def downgrade() -> None:
    raise NotImplementedError("Collapsing to user scope is one-way.")
