"""Team learning flips from opt-in to opt-out.

The spec settled on input-side consent: every uploaded session feeds the
team's collective distillation BY DEFAULT, and the per-session control is an
exclusion ("keep this one out of team memory"), not a share. Raw traces are
never team-readable either way — teammates see a transcript only via an
explicit per-person share. So `team_visible` (opt-in read grant + curator
input) is replaced by `team_memory_excluded` (curator input filter only).

No data carried forward: the flag shipped hours ago on a dev branch and the
old opt-in rows mean nothing under opt-out semantics.

Revision ID: 0187
Revises: 0186
"""

from alembic import op

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sessions_team_visible_idx")
    op.execute("ALTER TABLE sessions DROP COLUMN team_visible")
    op.execute(
        "ALTER TABLE sessions ADD COLUMN team_memory_excluded BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN team_memory_excluded")
    op.execute("ALTER TABLE sessions ADD COLUMN team_visible BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        "CREATE INDEX sessions_team_visible_idx ON sessions(owner_user_id, started_at DESC) "
        "WHERE team_visible AND deleted_at IS NULL"
    )
