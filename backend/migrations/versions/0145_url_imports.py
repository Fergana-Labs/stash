"""URL imports: out-of-band fetch jobs for URL-only clips.

A url_imports row is job state (like files.extraction_status), not a
product entity — the result is an ordinary page or file in the Clips tree.
import_batches groups the rows of one bookmarks.html or clip-all-tabs
import so progress can be reported per batch.

Revision ID: 0145
Revises: 0144
"""

from alembic import op

revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE import_batches (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind text NOT NULL,
            filename text,
            total integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE url_imports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_by uuid NOT NULL REFERENCES users(id),
            batch_id uuid REFERENCES import_batches(id) ON DELETE CASCADE,
            url text NOT NULL,
            title text,
            folder_id uuid REFERENCES folders(id) ON DELETE SET NULL,
            status text NOT NULL DEFAULT 'pending',
            error text,
            attempts integer NOT NULL DEFAULT 0,
            locked_at timestamptz,
            result_page_id uuid REFERENCES pages(id) ON DELETE SET NULL,
            result_file_id uuid REFERENCES files(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX url_imports_active_idx ON url_imports (created_at) "
        "WHERE status IN ('pending', 'processing')"
    )
    op.execute("CREATE INDEX url_imports_batch_idx ON url_imports (batch_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS url_imports")
    op.execute("DROP TABLE IF EXISTS import_batches")
