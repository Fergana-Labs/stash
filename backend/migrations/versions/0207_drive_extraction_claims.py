"""Reserve Drive extraction jobs before publishing and defer retries.

Revision ID: 0207
Revises: 0206
"""

from alembic import op

revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE drive_documents
            ADD COLUMN extraction_task_id text,
            ADD COLUMN extraction_claimed_at timestamptz,
            ADD COLUMN extraction_retry_at timestamptz NOT NULL DEFAULT now()
    """)
    # Old deliveries have no matching task ID. Reconcile queues current work.
    op.execute("""
        UPDATE drive_documents SET extraction_status =
            CASE WHEN extraction_attempts >= 3 THEN 'failed' ELSE 'pending' END,
            locked_at = NULL
        WHERE extraction_status = 'processing'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE drive_documents DROP COLUMN extraction_task_id,
            DROP COLUMN extraction_claimed_at, DROP COLUMN extraction_retry_at
    """)
