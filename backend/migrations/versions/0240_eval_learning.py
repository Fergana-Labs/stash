"""Eval learning: pinned regression examples and background improvement jobs.

Revision ID: 0240
Revises: 0239
"""

from alembic import op

revision = "0240"
down_revision = "0239"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A pinned example must stay correct; a version that gets it wrong cannot be saved
    # without an explicit override.
    op.execute("ALTER TABLE intuition_examples ADD COLUMN pinned boolean NOT NULL DEFAULT false")
    op.execute("""CREATE TABLE intuition_jobs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        kind text NOT NULL CHECK (kind IN ('improve')),
        status text NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
        progress jsonb NOT NULL DEFAULT '{}'::jsonb,
        result jsonb,
        error text,
        lease_until timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz
    )""")
    op.execute("CREATE INDEX intuition_jobs_model ON intuition_jobs(model_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE intuition_jobs")
    op.execute("ALTER TABLE intuition_examples DROP COLUMN pinned")
