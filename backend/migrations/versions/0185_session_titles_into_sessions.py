"""Fold session_titles into sessions — a title is a property of a session.

session_titles was a 1:1 side table (FK'd to sessions, same key) whose rows
only ever described the session they pointed at. Every reader had to LEFT
JOIN it, and every writer had to upsert against a table that could not exist
without its sessions row. Moving the columns onto sessions gives one row per
session with everything about it, and one codepath for reads and writes.

Carries existing titles forward in one shot, then drops the side table.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sessions
            ADD COLUMN title TEXT,
            ADD COLUMN title_source_hash TEXT,
            ADD COLUMN title_user_set BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN title_updated_at TIMESTAMPTZ
    """)
    op.execute("""
        UPDATE sessions s
        SET title = st.title,
            title_source_hash = st.source_hash,
            title_user_set = st.user_set,
            title_updated_at = st.updated_at
        FROM session_titles st
        WHERE st.owner_user_id = s.owner_user_id
          AND st.session_id = s.session_id
    """)
    op.execute("DROP TABLE session_titles")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE session_titles (
            owner_user_id UUID NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            user_set BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (owner_user_id, session_id),
            FOREIGN KEY (owner_user_id, session_id)
                REFERENCES sessions(owner_user_id, session_id)
                ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX idx_session_titles_updated ON session_titles(updated_at DESC)")
    op.execute("""
        INSERT INTO session_titles
            (owner_user_id, session_id, title, source_hash, user_set, updated_at)
        SELECT owner_user_id, session_id, title, title_source_hash,
               title_user_set, COALESCE(title_updated_at, now())
        FROM sessions
        WHERE title IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE sessions
            DROP COLUMN title,
            DROP COLUMN title_source_hash,
            DROP COLUMN title_user_set,
            DROP COLUMN title_updated_at
    """)
