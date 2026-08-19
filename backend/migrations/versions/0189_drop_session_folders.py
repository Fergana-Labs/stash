"""Drop session folders; carry externally-keyed ones forward as orgs.

Session folders did four jobs: grouping sessions in the UI, a public
share-by-slug page, bulk sharing a set of sessions, and telling the curator
which customer a session belonged to. Internal Multiplayer (the workspace) and
External Multiplayer (the org) now own the last two, sessions are already
shareable on their own, and the public page was never used — no row in
production ever had public_permission or discoverable set.

The one load-bearing job is `external_key`: a product backend calling
`session-folders/get-or-create` with its own customer id, which is exactly what
`orgs.external_id` is. Every keyed folder becomes an org, so those uploads keep
their per-customer boundary instead of losing it.

For each account owning keyed folders this creates, if absent, an invite-only
workspace scoped to that account (its data already lives there, and its API
keys are already minted on it, so nothing has to be re-keyed), activates the
developer platform on it, and turns each keyed folder into an org whose
sessions carry `org_id`. Unkeyed folders are UI grouping and simply go away.

Revision ID: 0189
Revises: 0188
"""

from alembic import op

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A workspace per account that owns keyed folders, scoped to that account.
    op.execute(
        """
        INSERT INTO workspaces (name, domain, scope_user_id, created_by)
        SELECT coalesce(nullif(u.display_name, ''), u.name), NULL, u.id, u.id
        FROM users u
        WHERE EXISTS (
            SELECT 1 FROM session_folders sf
            WHERE sf.owner_user_id = u.id AND sf.external_key IS NOT NULL
        )
        AND NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.scope_user_id = u.id)
        """
    )
    # A domainless workspace has no derived membership, so the owner needs an
    # explicit row or the workspace would be invisible to them.
    op.execute(
        """
        INSERT INTO workspace_members (workspace_id, user_id)
        SELECT w.id, w.created_by FROM workspaces w
        WHERE w.domain IS NULL AND w.created_by IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM workspace_members m
            WHERE m.workspace_id = w.id AND m.user_id = w.created_by
        )
        """
    )

    # Activate the developer platform and turn each keyed folder into an org.
    # A loop rather than chained CTEs because a folder's notepad has to be tied
    # to that exact folder: two of Heavi's keyed folders share a display name,
    # so any set-based join on name pairs the wrong notepad with the wrong org.
    op.execute(
        """
        DO $$
        DECLARE
            ws RECORD;
            fld RECORD;
            wiki_id uuid;
            notepads_id uuid;
            notepad_id uuid;
            new_org_id uuid;
        BEGIN
            FOR ws IN
                SELECT w.id, w.scope_user_id
                FROM workspaces w
                WHERE w.external_wiki_folder_id IS NULL
                AND EXISTS (
                    SELECT 1 FROM session_folders sf
                    WHERE sf.owner_user_id = w.scope_user_id
                    AND sf.external_key IS NOT NULL
                )
            LOOP
                INSERT INTO folders (owner_user_id, name, created_by, is_protected)
                VALUES (ws.scope_user_id, 'External Wiki', ws.scope_user_id, true)
                RETURNING id INTO wiki_id;

                INSERT INTO folders (owner_user_id, name, created_by, is_protected)
                VALUES (ws.scope_user_id, 'Org Notepads', ws.scope_user_id, true)
                RETURNING id INTO notepads_id;

                UPDATE workspaces
                SET external_wiki_folder_id = wiki_id, org_notepads_folder_id = notepads_id
                WHERE id = ws.id;
            END LOOP;

            FOR fld IN
                SELECT sf.id AS folder_id, sf.name, sf.external_key,
                       w.id AS workspace_id, w.scope_user_id, w.org_notepads_folder_id
                FROM session_folders sf
                JOIN workspaces w ON w.scope_user_id = sf.owner_user_id
                WHERE sf.external_key IS NOT NULL
            LOOP
                -- Named by external_key: folders are unique on
                -- (owner, parent, name) and two keyed folders share a name.
                INSERT INTO folders
                    (owner_user_id, parent_folder_id, name, created_by, is_protected)
                VALUES (fld.scope_user_id, fld.org_notepads_folder_id,
                        fld.external_key, fld.scope_user_id, true)
                RETURNING id INTO notepad_id;

                -- (workspace_id, external_id) is unique in the source, and orgs
                -- is new in 0188, so a conflict here means an assumption broke:
                -- let it raise rather than silently skip a customer.
                INSERT INTO orgs (workspace_id, external_id, name, notepad_folder_id)
                VALUES (fld.workspace_id, fld.external_key, fld.name, notepad_id)
                RETURNING id INTO new_org_id;

                UPDATE sessions
                SET org_id = new_org_id
                WHERE session_folder_id = fld.folder_id;
            END LOOP;
        END $$;
        """
    )

    op.execute("DELETE FROM shares WHERE object_type = 'session_folder'")
    op.execute("ALTER TABLE sessions DROP COLUMN session_folder_id")
    op.execute("DROP TABLE session_folders")


def downgrade() -> None:
    raise NotImplementedError("0188 drops session folders; restore from a backup instead")
