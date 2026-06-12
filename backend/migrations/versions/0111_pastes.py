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
            comments_enabled BOOLEAN NOT NULL DEFAULT true,
            view_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute("CREATE INDEX idx_pastes_created ON pastes (created_at DESC)")
    # Anonymous selection-anchored comments. quoted/prefix/suffix capture
    # the selected range app-style, without mutating the page content.
    op.execute("""
        CREATE TABLE paste_comments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            paste_id UUID NOT NULL REFERENCES pastes(id) ON DELETE CASCADE,
            author_name TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            quoted_text TEXT NOT NULL DEFAULT '',
            prefix TEXT NOT NULL DEFAULT '',
            suffix TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute("CREATE INDEX idx_paste_comments_paste ON paste_comments (paste_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE paste_comments")
    op.execute("DROP TABLE pastes")
