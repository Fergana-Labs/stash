"""Remove persona concept: drop persona satellite tables, persona-only user columns, user type.

Personas (agent-identity users with API key rotation, watch/inject/sleep flows)
were deprecated in PR25. This migration removes their remaining schema footprint:

- Drops satellite tables: chat_watches, injection_configs, injection_sessions, sleep_configs
- Drops persona-only user columns: owner_id, notebook_id, history_id
- Drops users.type column + CHECK constraint (all remaining users are human)

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_watches CASCADE")
    op.execute("DROP TABLE IF EXISTS injection_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS injection_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS sleep_configs CASCADE")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS owner_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS notebook_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS history_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS type")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN type VARCHAR(8) "
        "NOT NULL DEFAULT 'human' CHECK(type IN ('human', 'persona'))"
    )
    op.execute("ALTER TABLE users ADD COLUMN history_id UUID")
    op.execute("ALTER TABLE users ADD COLUMN notebook_id UUID")
    op.execute(
        "ALTER TABLE users ADD COLUMN owner_id UUID "
        "REFERENCES users(id) ON DELETE CASCADE"
    )
