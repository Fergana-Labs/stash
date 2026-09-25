"""Name recorded sessions after their harness, not the recorder's login handle."""

from alembic import op

revision = "0227"
down_revision = "0226"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH clients AS (
            SELECT DISTINCT ON (owner_user_id,session_id)
                owner_user_id,session_id,metadata->>'client' AS client
            FROM history_events WHERE metadata ? 'client' AND session_id IS NOT NULL
            ORDER BY owner_user_id,session_id,created_at DESC,id DESC
        )
        UPDATE sessions s SET agent_name=CASE c.client
            WHEN 'claude_code' THEN 'Claude Code' WHEN 'codex_cli' THEN 'Codex'
            WHEN 'cursor' THEN 'Cursor' WHEN 'opencode' THEN 'OpenCode'
            WHEN 'gemini_cli' THEN 'Gemini CLI' WHEN 'openclaw' THEN 'OpenClaw'
            WHEN 'hermes' THEN 'Hermes' ELSE c.client END
        FROM clients c WHERE s.owner_user_id=c.owner_user_id AND s.session_id=c.session_id
            AND c.client IS NOT NULL
    """)


def downgrade() -> None:
    pass
