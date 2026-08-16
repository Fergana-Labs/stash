"""Multiplier: the two consent switches for team sharing.

Internal multiplayer ("Multiplier") is built on explicit contribution:
nothing a person does reaches teammates unless they chose it. Two booleans
carry that choice:

- `users.session_uploads_enabled` — the master switch. Off means the
  account accepts no new session transcripts at all; upload endpoints
  reject with an explicit 403 rather than silently dropping events.
- `sessions.team_visible` — the per-session choice. On means workspace
  co-members may read this session (and the team curator may learn from
  it). Off — the default — keeps it private to its owner, always.

Visibility on sessions is otherwise computed from shares at read time;
this flag is stored because "shared with my team" is a standing property
of the session, not a per-principal grant.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN session_uploads_enabled BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE sessions ADD COLUMN team_visible BOOLEAN NOT NULL DEFAULT false")
    # Team views list co-members' shared sessions, newest first.
    op.execute(
        "CREATE INDEX sessions_team_visible_idx ON sessions(owner_user_id, started_at DESC) "
        "WHERE team_visible AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sessions_team_visible_idx")
    op.execute("ALTER TABLE sessions DROP COLUMN team_visible")
    op.execute("ALTER TABLE users DROP COLUMN session_uploads_enabled")
