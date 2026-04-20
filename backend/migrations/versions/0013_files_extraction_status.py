"""Add extraction status columns to files; move text extraction off the upload
request path.

Why: synchronous extraction inside the upload handler caused OOM kills on
Render's Starter plan when scanned PDFs triggered tesseract / pypdfium2. This
migration introduces a per-file job state so a background dispatcher in the
same process can pick up pending files and run extraction in a child process
with its own RLIMIT_AS, keeping web responsive.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE files "
        "ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'pending', "
        "ADD COLUMN IF NOT EXISTS extraction_error TEXT, "
        "ADD COLUMN IF NOT EXISTS extraction_attempts INT NOT NULL DEFAULT 0, "
        "ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ"
    )

    # Files that already have extracted_text are done — don't re-run them.
    op.execute(
        "UPDATE files SET extraction_status = 'done' WHERE extracted_text IS NOT NULL"
    )

    # Partial index so the dispatcher's claim query stays fast as the
    # backlog grows. Covers (pending | failed-with-retries-left) rows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_extraction_pending "
        "ON files(extraction_status, extraction_attempts, locked_at) "
        "WHERE extraction_status IN ('pending', 'failed')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_extraction_pending")
    op.execute(
        "ALTER TABLE files "
        "DROP COLUMN IF EXISTS locked_at, "
        "DROP COLUMN IF EXISTS extraction_attempts, "
        "DROP COLUMN IF EXISTS extraction_error, "
        "DROP COLUMN IF EXISTS extraction_status"
    )
