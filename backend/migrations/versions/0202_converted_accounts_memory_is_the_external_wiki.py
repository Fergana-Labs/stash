"""A converted account's Memory wiki becomes its External Wiki.

An account that filed sessions into externally-keyed folders was running
External Multiplayer before it existed: its "internal" Memory wiki was built
from customer sessions and read by every customer's agent — external memory
on personal-memory machinery. 0201 gave such accounts an empty External
Wiki; this carries the mature one forward instead of making customers'
agents start from nothing while a rebuild catches up.

Three moves per converted workspace (scope owns keyed folders):
- The Memory folder's contents — subfolders, pages, files — re-parent into
  the External Wiki folder. The Memory folder itself stays, empty.
- The external curator inherits the internal curator's watermark: the moved
  content is already curated through it, so the first external run continues
  incrementally instead of re-chewing the full history.
- The internal curator is paused (run_mode 'chat' — the scheduler only fires
  scheduled agents). These accounts are exclusively External Multiplayer:
  every session carries an end user, so there is no internal material, and
  an active internal curator would only re-derive customer knowledge into a
  fresh Memory wiki nightly. The row stays for its run history.

Revision ID: 0202
Revises: 0201
"""

from alembic import op

revision = "0202"
down_revision = "0201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            ws RECORD;
            memory_id uuid;
            internal RECORD;
        BEGIN
            FOR ws IN
                SELECT w.id, w.scope_user_id, w.external_wiki_folder_id
                FROM workspaces w
                WHERE w.external_wiki_folder_id IS NOT NULL
                AND EXISTS (
                    SELECT 1 FROM session_folders sf
                    WHERE sf.owner_user_id = w.scope_user_id
                    AND sf.external_key IS NOT NULL
                )
            LOOP
                SELECT id INTO memory_id FROM folders
                WHERE owner_user_id = ws.scope_user_id AND is_memory;

                IF memory_id IS NOT NULL THEN
                    UPDATE folders SET parent_folder_id = ws.external_wiki_folder_id
                    WHERE parent_folder_id = memory_id;
                    UPDATE pages SET folder_id = ws.external_wiki_folder_id
                    WHERE folder_id = memory_id;
                    UPDATE files SET folder_id = ws.external_wiki_folder_id
                    WHERE folder_id = memory_id;
                END IF;

                SELECT curated_through, last_run_at INTO internal FROM agents
                WHERE user_id = ws.scope_user_id AND is_curator
                  AND curator_wiki = 'internal';

                IF internal.curated_through IS NOT NULL THEN
                    UPDATE agents
                    SET curated_through = GREATEST(curated_through, internal.curated_through),
                        last_run_at = GREATEST(last_run_at, internal.last_run_at)
                    WHERE user_id = ws.scope_user_id AND is_curator
                      AND curator_wiki = 'external';
                END IF;

                UPDATE agents SET run_mode = 'chat'
                WHERE user_id = ws.scope_user_id AND is_curator
                  AND curator_wiki = 'internal';
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "0202 folds a converted account's Memory wiki into its External Wiki; "
        "restore from a backup instead"
    )
