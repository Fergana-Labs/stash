"""Track user-owned async tasks returned to clients.

Revision ID: 0103
Revises: 0102
"""

from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE task_records (
            task_id      varchar(255) PRIMARY KEY,
            user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
            task_type    varchar(64) NOT NULL,
            object_type  varchar(64),
            object_id    uuid,
            created_at   timestamptz NOT NULL DEFAULT now()
        )
        """)
    op.execute("CREATE INDEX task_records_user_idx ON task_records (user_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_records")
