"""Convert keyed session folders into developer-platform end users.

The Heavi cutover, generalized: any account whose backend files sessions into
externally-keyed session folders becomes a developer workspace, and each keyed
folder becomes an `end_users` row carrying the same external id, so uploads
keep their per-customer boundary. Existing sessions are stamped with the new
`end_user_id`. Unkeyed folders are UI grouping and are left alone.

This is the convert half of what 0190 originally attempted (that revision is
now a no-op; its docstring tells the story). Nothing is dropped and nothing
is refused: the folders stay, so the customer's old backend keeps writing
through the legacy lane while their user_id-based code rolls out — the
cutover has no window where writes fail. Legacy-lane sessions written after
this migration lack `end_user_id` until the sunset migration, whose FIRST
statement must re-run this migration's session UPDATE as a sweep (it is
idempotent — `end_user_id IS NULL` guards it) before dropping the
session_folders table, the `session_folder_id` column, and the legacy read
aliases. test_legacy_lane_coexistence.py pins the properties the sweep
relies on.

The workspace is scoped to the existing account itself, not a fresh scope
user: the account's data and API keys already live there, so nothing has to
be re-keyed and the customer's credentials keep working across the cutover.

Revision ID: 0201
Revises: 0200
"""

from alembic import op

revision = "0201"
down_revision = "0200"
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
    # A domainless workspace has no derived membership, so the account needs
    # an explicit member row or the console gate would never open for it.
    op.execute(
        """
        INSERT INTO workspace_members (workspace_id, user_id)
        SELECT w.id, w.scope_user_id FROM workspaces w
        WHERE EXISTS (
            SELECT 1 FROM session_folders sf
            WHERE sf.owner_user_id = w.scope_user_id AND sf.external_key IS NOT NULL
        )
        AND NOT EXISTS (
            SELECT 1 FROM workspace_members m
            WHERE m.workspace_id = w.id AND m.user_id = w.scope_user_id
        )
        """
    )

    # Activate the developer platform and turn each keyed folder into an end
    # user. A loop rather than chained CTEs because a folder's wiki has to
    # be tied to that exact folder: two of Heavi's keyed folders share a
    # display name, so any set-based join on name pairs the wrong wiki folder
    # with the wrong end user.
    op.execute(
        """
        DO $$
        DECLARE
            ws RECORD;
            fld RECORD;
            wiki_id uuid;
            wikis_id uuid;
            user_wiki_id uuid;
            eu_id uuid;
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
                VALUES (ws.scope_user_id, 'User Wikis', ws.scope_user_id, true)
                RETURNING id INTO wikis_id;

                UPDATE workspaces
                SET external_wiki_folder_id = wiki_id,
                    end_user_wikis_folder_id = wikis_id
                WHERE id = ws.id;
            END LOOP;

            FOR fld IN
                SELECT sf.id AS folder_id, sf.name, sf.external_key,
                       w.id AS workspace_id, w.scope_user_id,
                       w.end_user_wikis_folder_id
                FROM session_folders sf
                JOIN workspaces w ON w.scope_user_id = sf.owner_user_id
                WHERE sf.external_key IS NOT NULL
            LOOP
                -- An end user with this external id already exists only when
                -- the account activated the platform and wrote for the same
                -- customer through both lanes; that is the same customer, so
                -- the existing row wins and the folder's sessions join it.
                SELECT id INTO eu_id FROM end_users
                WHERE workspace_id = fld.workspace_id
                  AND external_id = fld.external_key;

                IF eu_id IS NULL THEN
                    -- Named by external_key: folders are unique on
                    -- (owner, parent, name) and two keyed folders share a name.
                    INSERT INTO folders
                        (owner_user_id, parent_folder_id, name, created_by, is_protected)
                    VALUES (fld.scope_user_id, fld.end_user_wikis_folder_id,
                            fld.external_key, fld.scope_user_id, true)
                    RETURNING id INTO user_wiki_id;

                    INSERT INTO end_users (workspace_id, external_id, name, wiki_folder_id)
                    VALUES (fld.workspace_id, fld.external_key, fld.name, user_wiki_id)
                    RETURNING id INTO eu_id;
                END IF;

                UPDATE sessions
                SET end_user_id = eu_id
                WHERE session_folder_id = fld.folder_id AND end_user_id IS NULL;
            END LOOP;
        END $$;
        """
    )

    # Workspaces activated here never went through the activate endpoint, so
    # nothing provisioned their external curator — without one their users'
    # sessions would never be curated until someone opened the console. Same
    # seed as 0193; the stagger only needs to land inside the nightly window.
    op.execute(
        """
        INSERT INTO agents (user_id, name, run_mode, schedule_cron, is_curator,
                            curator_wiki, last_run_at, curated_through)
        SELECT w.scope_user_id, 'External wiki curator', 'scheduled',
               (abs(hashtext(w.scope_user_id::text)) % 60)::text || ' ' ||
               (8 + (abs(hashtext(w.scope_user_id::text)) / 60) % 4)::text || ' * * *',
               true, 'external',
               greatest(u.created_at, now() - interval '90 days'),
               greatest(u.created_at, now() - interval '90 days')
        FROM workspaces w
        JOIN users u ON u.id = w.scope_user_id
        WHERE w.external_wiki_folder_id IS NOT NULL
        ON CONFLICT (user_id, curator_wiki) WHERE is_curator DO NOTHING
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "0201 folds keyed session folders into the developer platform; restore from a backup instead"
    )
