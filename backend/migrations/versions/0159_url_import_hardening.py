"""Bulk-import hardening: retry/dispatch bookkeeping and link-only saves.

url_imports gains retry_at (rate-limited rows wait instead of burning an
attempt) and dispatched_at (the dispatcher caps in-flight batches, so it
must know what is already out). A new needs_client status marks rows the
server cannot fetch (401/403, exhausted rate limits) that the extension
retries from the user's browser; the partial index serves the extension's
per-user polling endpoint.

Existing Bookmarks tables also learn the "Link" type so imports that never
yield readable content can still be indexed as a bare link row.

Revision ID: 0159
Revises: 0158
"""

from alembic import op

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE url_imports ADD COLUMN retry_at timestamptz")
    op.execute("ALTER TABLE url_imports ADD COLUMN dispatched_at timestamptz")
    op.execute(
        "CREATE INDEX url_imports_needs_client_idx "
        "ON url_imports (owner_user_id, created_at) "
        "WHERE status = 'needs_client'"
    )
    # One-shot data migration: existing Bookmarks tables were created before
    # the "Link" type existed; row validation rejects values outside the
    # stored options, so append it everywhere it's missing.
    op.execute(
        """
        UPDATE tables
        SET columns = (
            SELECT jsonb_agg(
                CASE
                    WHEN col->>'name' = 'Type'
                         AND NOT (col->'options' ? 'Link')
                    THEN jsonb_set(col, '{options}', (col->'options') || '"Link"')
                    ELSE col
                END
            )
            FROM jsonb_array_elements(columns) AS col
        )
        WHERE name = 'Bookmarks'
          AND columns @> '[{"name": "Type"}]'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS url_imports_needs_client_idx")
    op.execute("ALTER TABLE url_imports DROP COLUMN IF EXISTS dispatched_at")
    op.execute("ALTER TABLE url_imports DROP COLUMN IF EXISTS retry_at")
