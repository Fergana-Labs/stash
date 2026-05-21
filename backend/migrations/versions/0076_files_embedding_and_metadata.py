"""Page/file parity: files get embedding, embed_stale, metadata.

Pages already carry an `embedding vector(384)` + `embed_stale boolean` so
they show up in the embedding map and feed semantic search. Files
already carry `extracted_text`, but no embedding — they're invisible to
the same surfaces. This migration closes that gap: a follow-up worker
batch consumes `extracted_text` and writes the embedding.

`metadata jsonb` mirrors `pages.metadata` so files can carry the same
kind of side-band state (e.g. `shared_in_stash_id`) when we need it.

Revision ID: 0076
Revises: 0075
Create Date: 2026-05-21
"""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE files "
        "ADD COLUMN IF NOT EXISTS embedding vector(384), "
        "ADD COLUMN IF NOT EXISTS embed_stale boolean NOT NULL DEFAULT FALSE, "
        "ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    # Mark every file that already has extracted text so the embedding
    # reconciler picks it up on its next pass.
    op.execute(
        "UPDATE files SET embed_stale = TRUE "
        "WHERE extracted_text IS NOT NULL AND extracted_text <> '' "
        "AND deleted_at IS NULL"
    )
    # Partial index matches the reconciler's hot path.
    op.execute("CREATE INDEX IF NOT EXISTS idx_files_embed_stale " "ON files(id) WHERE embed_stale")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_embed_stale")
    op.execute(
        "ALTER TABLE files "
        "DROP COLUMN IF EXISTS embedding, "
        "DROP COLUMN IF EXISTS embed_stale, "
        "DROP COLUMN IF EXISTS metadata"
    )
