"""Invalidate shared knowledge compiled before an existing user's opt-out.

Revision ID: 0204
Revises: 0203
"""

from alembic import op

revision = "0204"
down_revision = "0203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ADD COLUMN curation_generation integer NOT NULL DEFAULT 0")
    # Old pages have no input provenance. Preserve the corpus privately and
    # rebuild from permitted inputs instead of guessing which text is safe.
    op.execute("""
        DO $$
        DECLARE ws RECORD; new_root uuid; old_ids uuid[];
        BEGIN
          FOR ws IN SELECT w.* FROM workspaces w
            WHERE w.external_wiki_folder_id IS NOT NULL
            AND EXISTS (SELECT 1 FROM end_users e WHERE e.workspace_id = w.id
                        AND NOT e.share_wiki)
          LOOP
            WITH RECURSIVE tree AS (
              SELECT id FROM folders WHERE id = ws.external_wiki_folder_id
              UNION ALL
              SELECT f.id FROM folders f JOIN tree t ON f.parent_folder_id = t.id
            ) SELECT array_agg(id) INTO old_ids FROM tree;
            UPDATE folders SET public_permission = 'none' WHERE id = ANY(old_ids);
            UPDATE pages SET public_permission = 'none' WHERE folder_id = ANY(old_ids);
            UPDATE files SET public_permission = 'none' WHERE folder_id = ANY(old_ids);
            UPDATE tables SET public_permission = 'none' WHERE folder_id = ANY(old_ids);
            DELETE FROM shares WHERE object_id = ANY(old_ids)
              OR object_id IN (SELECT id FROM pages WHERE folder_id = ANY(old_ids))
              OR object_id IN (SELECT id FROM files WHERE folder_id = ANY(old_ids))
              OR object_id IN (SELECT id FROM tables WHERE folder_id = ANY(old_ids));
            DELETE FROM skills WHERE folder_id = ANY(old_ids);
            UPDATE files SET end_user_id = NULL WHERE folder_id = ANY(old_ids);
            UPDATE folders SET name = 'Shared wiki archive (' || id || ')', parent_folder_id = NULL
              WHERE id = ws.external_wiki_folder_id;
            INSERT INTO folders (owner_user_id, created_by, name, is_protected)
              VALUES (ws.scope_user_id, ws.scope_user_id, 'External Wiki', true)
              RETURNING id INTO new_root;
            UPDATE workspaces SET external_wiki_folder_id = new_root,
              curation_generation = curation_generation + 1 WHERE id = ws.id;
            UPDATE agents SET curated_through = NULL
              WHERE user_id = ws.scope_user_id AND curator_wiki = 'external';
          END LOOP;
        END $$;
    """)


def downgrade() -> None:
    raise NotImplementedError(
        "Restoring shared knowledge after an opt-out would expose private data"
    )
