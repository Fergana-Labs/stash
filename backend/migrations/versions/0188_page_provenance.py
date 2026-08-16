"""Pages remember which sessions they were built from.

Provenance is the mechanism behind two spec obligations that were previously
prompt-only hopes:

- **Honest opt-out.** Excluding a session from team memory must reach content
  already derived from it. `page_sources` finds those pages;
  `pages.needs_recuration` marks them for the curator's next run.
- **Enforced promotion.** A Team Skills page requires >=2 distinct authors'
  sessions behind it. With sources recorded, that bar is checked at write
  time instead of trusted to the curator's prompt.

Revision ID: 0188
Revises: 0187
"""

from alembic import op

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE page_sources (
            page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            session_owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (page_id, session_owner_user_id, session_id)
        )
        """
    )
    # Exclusion flips look up "which pages used this session".
    op.execute(
        "CREATE INDEX page_sources_session_idx ON page_sources (session_owner_user_id, session_id)"
    )
    op.execute("ALTER TABLE pages ADD COLUMN needs_recuration BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE pages DROP COLUMN needs_recuration")
    op.execute("DROP TABLE page_sources")
