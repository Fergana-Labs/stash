"""Comments on a proposed rubric change.

A proposed change (eval_rubric_proposals) is discussed before it is decided, the way a pull
request is. Each comment belongs to one proposal; trait names the rubric trait it is about,
empty when it is about the change as a whole.

Revision ID: 0259
Revises: 0258
"""

from alembic import op

revision = "0259"
down_revision = "0258"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE eval_rubric_proposal_comments (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        proposal_id uuid NOT NULL REFERENCES eval_rubric_proposals(id) ON DELETE CASCADE,
        author uuid REFERENCES users(id) ON DELETE SET NULL,
        trait text NOT NULL DEFAULT '',
        body text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX eval_rubric_proposal_comments_proposal "
        "ON eval_rubric_proposal_comments (proposal_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE eval_rubric_proposal_comments")
