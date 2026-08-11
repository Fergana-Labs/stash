"""The hopper: a ledger of everything dropped in, and where it landed.

A hopper item stores no content of its own. Each drop goes down whichever
existing pipeline can make it legible — bytes through the files/pages ingest,
a URL through url_imports, typed text straight into a page — and the row here
only records which drop became which target. Legibility is therefore never
written twice: the feed reads it live off files.extraction_status and
url_imports.status, which stay the single source of truth.

Exactly one target column is set per row, decided at drop time by kind.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE hopper_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_by uuid NOT NULL REFERENCES users(id),
            kind text NOT NULL CHECK (kind IN ('file', 'link', 'note')),
            label text NOT NULL,
            page_id uuid REFERENCES pages(id) ON DELETE CASCADE,
            file_id uuid REFERENCES files(id) ON DELETE CASCADE,
            url_import_id uuid REFERENCES url_imports(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX hopper_items_owner_idx ON hopper_items (owner_user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS hopper_items")
