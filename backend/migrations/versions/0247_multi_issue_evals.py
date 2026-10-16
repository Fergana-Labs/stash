"""Allow multi-issue evals in databases that already applied judge curation.

Revision ID: 0247
Revises: 0246
"""

from alembic import op

revision = "0247"
down_revision = "0246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE intuition_models DROP CONSTRAINT intuition_models_output_type_check")
    op.execute(
        "ALTER TABLE intuition_models ADD CONSTRAINT intuition_models_output_type_check "
        "CHECK (output_type IN ('choice', 'preference', 'multi'))"
    )


def downgrade() -> None:
    # Refuse a rollback that would make persisted models invalid rather than
    # silently deleting or changing the owner's multi-issue evals.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM intuition_models WHERE output_type = 'multi') THEN
            RAISE EXCEPTION 'Cannot downgrade while multi-issue evals exist';
        END IF;
    END $$""")
    op.execute("ALTER TABLE intuition_models DROP CONSTRAINT intuition_models_output_type_check")
    op.execute(
        "ALTER TABLE intuition_models ADD CONSTRAINT intuition_models_output_type_check "
        "CHECK (output_type IN ('choice', 'preference'))"
    )
