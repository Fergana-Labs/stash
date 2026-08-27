"""Record when each useful session trace was curated."""

from alembic import op

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN curated_at timestamptz")
    op.execute(
        """
        UPDATE sessions s
        SET curated_at = a.curated_through
        FROM agents a
        WHERE a.user_id = s.owner_user_id
          AND a.is_curator
          AND a.curator_wiki = 'internal'
          AND a.curated_through IS NOT NULL
          AND s.last_event_at <= a.curated_through
          AND s.deleted_at IS NULL
          AND s.session_id NOT LIKE 'agent-curate-%'
          AND EXISTS (
              SELECT 1 FROM history_events he
              WHERE he.owner_user_id = s.owner_user_id
                AND he.session_id = s.session_id
                AND he.event_type = 'assistant_message'
          )
        """
    )
    op.execute(
        "CREATE INDEX idx_sessions_curated_at "
        "ON sessions(owner_user_id, curated_at) WHERE curated_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_sessions_curated_at")
    op.execute("ALTER TABLE sessions DROP COLUMN curated_at")
