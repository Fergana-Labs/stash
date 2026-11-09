"""Record who added each eval example, through what, and from which agent session.

added_by: the user whose request added it. added_via: 'web' (the app) or 'api' (an API key,
which is how agents add examples). caller: the agent's own name for itself, as score calls
already record it. session_id: the agent's session id, linked to its Stash session when that
session was tracked.
"""

from alembic import op

revision = "0257"
down_revision = "0256"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE intuition_examples
            ADD COLUMN added_by uuid REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN added_via text NOT NULL DEFAULT '',
            ADD COLUMN caller text NOT NULL DEFAULT '',
            ADD COLUMN session_id text
    """)
    # Until now only an eval's owner could add to it.
    op.execute("""
        UPDATE intuition_examples e SET added_by = m.owner_user_id
        FROM intuition_models m WHERE m.id = e.model_id
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE intuition_examples
            DROP COLUMN session_id,
            DROP COLUMN caller,
            DROP COLUMN added_via,
            DROP COLUMN added_by
    """)
