"""Drop flat-path X save orphans left by the folders rollout.

During the 0156 deploy, the pre-folders worker finished an in-flight sync on
warm shutdown and inserted a batch of X posts with the old flat path (just the
tweet id, no kind folder). The new worker then re-backfilled the same tweets
under Posts/<id>, so every flat row is a content-less pending duplicate of a
foldered twin — it only shows up as a stray "Loading…" row at the source root.
Delete the flat rows; the foldered copies carry the real data.

Revision ID: 0157
Revises: 0156
"""

from alembic import op

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM x_save_docs WHERE path NOT LIKE '%/%'")


def downgrade() -> None:
    # The deleted rows were content-less duplicates; there is nothing to restore.
    pass
