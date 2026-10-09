"""Identify copied Drive documents by file ID, not their non-unique names."""

from alembic import op

revision = "0228"
down_revision = "0227"
branch_labels = None
depends_on = None


def upgrade():
    # A rename interrupted before the old path was swept can leave two cache
    # rows for one upstream file. Keep the newest version, preferring a live,
    # extracted copy. These are provider caches, not authored Stash documents.
    op.execute("""
        DELETE FROM drive_documents WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY source_id, external_ref
                    ORDER BY (deleted_at IS NULL) DESC,
                        external_updated_at DESC NULLS LAST,
                        (content IS NOT NULL) DESC, updated_at DESC, id
                ) AS position
                FROM drive_documents WHERE external_ref IS NOT NULL
            ) copies WHERE position > 1
        )
    """)
    op.execute("""
        ALTER TABLE drive_documents
            ADD CONSTRAINT drive_documents_source_id_external_ref_key
                UNIQUE (source_id, external_ref),
            DROP CONSTRAINT drive_documents_source_id_path_key,
            ADD CONSTRAINT drive_documents_source_id_path_key
                UNIQUE (source_id, path) DEFERRABLE INITIALLY IMMEDIATE
    """)


def downgrade():
    op.execute("""
        ALTER TABLE drive_documents
            DROP CONSTRAINT drive_documents_source_id_external_ref_key,
            DROP CONSTRAINT drive_documents_source_id_path_key,
            ADD CONSTRAINT drive_documents_source_id_path_key UNIQUE (source_id, path)
    """)
