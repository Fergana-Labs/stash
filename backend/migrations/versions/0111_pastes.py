"""Anonymous public pastes — the joinstash.ai/pages pastebin.

Each row is a standalone published page (markdown or mini HTML site)
created without an account. Publishing always yields two URLs: the
public view link and a private edit link carrying the plaintext
``edit_token`` — the only write credential, returned once at create
time and never read back out through the public API. ``visibility``
controls the public feed (unlisted pages stay link-only). Private pages
don't exist here — that's the signup gate into the product.

Revision ID: 0111
Revises: 0110
"""

from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pastes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            edit_token TEXT NOT NULL,
            title TEXT NOT NULL,
            content_type VARCHAR(8) NOT NULL
                CONSTRAINT pastes_content_type_check
                CHECK (content_type IN ('markdown', 'html')),
            content TEXT NOT NULL,
            visibility VARCHAR(8) NOT NULL DEFAULT 'public'
                CONSTRAINT pastes_visibility_check
                CHECK (visibility IN ('public', 'unlisted')),
            view_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute("CREATE INDEX idx_pastes_created ON pastes (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE pastes")
