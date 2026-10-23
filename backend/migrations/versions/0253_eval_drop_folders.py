"""Drop folders for evals: a Files folder whose new files and pages become unlabeled examples.

intuition_models.drop_folder_id is the eval's folder (cleared if the folder is deleted).
intuition_drop_imports records every file or page already taken from it, with the
example it became or why it could not be read, so nothing is imported twice.

Revision ID: 0253
Revises: 0252
"""

from alembic import op

revision = "0253"
down_revision = "0252"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE intuition_models "
        "ADD COLUMN drop_folder_id uuid REFERENCES folders(id) ON DELETE SET NULL"
    )
    op.execute(
        """CREATE TABLE intuition_drop_imports (
             model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
             object_type text NOT NULL CHECK (object_type IN ('file', 'page')),
             object_id uuid NOT NULL,
             example_id uuid REFERENCES intuition_examples(id) ON DELETE SET NULL,
             error text,
             imported_at timestamptz NOT NULL DEFAULT now(),
             PRIMARY KEY (model_id, object_type, object_id)
           )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE intuition_drop_imports")
    op.execute("ALTER TABLE intuition_models DROP COLUMN drop_folder_id")
