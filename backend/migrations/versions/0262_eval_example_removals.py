"""Keep a record of labeled examples taken out of an eval.

Removing an example deletes its row, so nothing was left to say that a rubric change followed
from an example being taken away. eval_example_removals keeps what was removed (the item, its
label and note), who removed it and when, so a rubric change can list the examples removed
since the version it was made on beside the ones added.

Revision ID: 0262
Revises: 0261
"""

from alembic import op

revision = "0262"
down_revision = "0261"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE eval_example_removals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        example_id uuid NOT NULL,
        item jsonb NOT NULL,
        label text NOT NULL,
        note text NOT NULL DEFAULT '',
        added_at timestamptz,
        removed_by uuid REFERENCES users(id) ON DELETE SET NULL,
        removed_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX eval_example_removals_model ON eval_example_removals (model_id, removed_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE eval_example_removals")
