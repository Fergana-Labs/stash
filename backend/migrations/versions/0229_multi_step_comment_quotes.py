"""Allow one comment to quote multiple trace steps.

Revision ID: 0229
Revises: 0228
"""

from alembic import op

revision = "0229"
down_revision = "0228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE rm_annotations DROP CONSTRAINT rm_annotations_quote_requires_step")
    op.execute("""
        ALTER TABLE rm_annotations ADD CONSTRAINT rm_annotations_quote_requires_step CHECK (
            quote IS NULL OR step_id IS NOT NULL OR (
                rating IS NULL AND comment IS NOT NULL AND
                CASE WHEN jsonb_typeof(quote->'segments') = 'array'
                    THEN jsonb_array_length(quote->'segments') >= 2
                    ELSE false END
            )
        )
    """)


def downgrade() -> None:
    # Preserve comments as trace comments when reverting to the single-step format.
    op.execute("UPDATE rm_annotations SET quote = NULL WHERE step_id IS NULL AND quote IS NOT NULL")
    op.execute("ALTER TABLE rm_annotations DROP CONSTRAINT rm_annotations_quote_requires_step")
    op.execute("""
        ALTER TABLE rm_annotations ADD CONSTRAINT rm_annotations_quote_requires_step
        CHECK (quote IS NULL OR step_id IS NOT NULL)
    """)
