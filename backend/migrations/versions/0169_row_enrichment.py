"""Mini programs: enrichment + first-class identity for app-shaped tables.

`tables.mini_program` holds a manifest slug ("bookmarks"). It is what makes
/apps/<slug> a lookup instead of a name match, and what lets the UI pick an
app shell rather than the generic grid. A NULL means an ordinary table.

Enrichment: LLM-derived columns on table rows.

Mirrors the embedding reconciler's shape (0016): a per-row stale flag plus a
content hash so unchanged rows are never re-enriched, and a partial index so
the beat sweep's `WHERE enrich_stale` scan stays cheap.

`enrichment_config` on tables is the per-table manifest the worker reads:
which column holds the source text, and which columns the model fills.
Sibling of the existing `embedding_config`.

`enrich_error` records why a row was abandoned. The sweep clears the stale
flag when it gives up, so a poison row can't wedge the batch — the error is
recorded rather than swallowed.
"""

from alembic import op

revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tables "
        "ADD COLUMN IF NOT EXISTS enrichment_config JSONB, "
        "ADD COLUMN IF NOT EXISTS mini_program TEXT"
    )
    # One mini-program table per slug per owner: the slug route resolves to
    # exactly one table, and a lost get-or-create race can't fork a user's
    # Bookmarks into two.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tables_mini_program_owner "
        "ON tables(owner_user_id, mini_program) WHERE mini_program IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE table_rows "
        "ADD COLUMN IF NOT EXISTS enrich_stale BOOLEAN NOT NULL DEFAULT FALSE, "
        "ADD COLUMN IF NOT EXISTS enrich_hash TEXT, "
        "ADD COLUMN IF NOT EXISTS enrich_error TEXT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_table_rows_enrich_stale "
        "ON table_rows(id) WHERE enrich_stale"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_table_rows_enrich_stale")
    op.execute(
        "ALTER TABLE table_rows "
        "DROP COLUMN IF EXISTS enrich_stale, "
        "DROP COLUMN IF EXISTS enrich_hash, "
        "DROP COLUMN IF EXISTS enrich_error"
    )
    op.execute("DROP INDEX IF EXISTS idx_tables_mini_program_owner")
    op.execute(
        "ALTER TABLE tables "
        "DROP COLUMN IF EXISTS enrichment_config, "
        "DROP COLUMN IF EXISTS mini_program"
    )
