"""Remove website taste and image evals; evals become one system on Intuitions.

Drops the tables of the two separate eval systems (website taste from 0249, image evals
from 0250). They were empty in production when removed, and nothing reads them now.

Revision ID: 0251
Revises: 0250
"""

from alembic import op

revision = "0251"
down_revision = "0250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "image_eval_examples",
        "image_eval_calls",
        "image_evals",
        "taste_predictions",
        "taste_jobs",
        "taste_workspaces",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    raise NotImplementedError(
        "Recreating the removed website taste and image eval tables is not supported"
    )
