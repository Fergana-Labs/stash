"""Instagram saves carry a media array, like X saves already do.

A carousel post has up to ten images or videos; the single
`media_storage_key` column could hold one, so the other nine were dropped
silently. X solved this already — `x_save_docs.media` is a JSONB array of
`{storage_key, content_type}` — so Instagram adopts the same shape rather
than growing a second one.

The two scalar columns are migrated into the array and then dropped: one
column, one reader, no dual path. Rows whose media never archived get `[]`,
which is what "no media stored" already meant.
"""

from alembic import op

revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE instagram_save_docs "
        "ADD COLUMN IF NOT EXISTS media JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        """
        UPDATE instagram_save_docs
        SET media = jsonb_build_array(
            jsonb_build_object(
                'storage_key', media_storage_key,
                'content_type', COALESCE(media_content_type, 'application/octet-stream')
            )
        )
        WHERE media_storage_key IS NOT NULL AND media = '[]'::jsonb
        """
    )
    op.execute(
        "ALTER TABLE instagram_save_docs "
        "DROP COLUMN IF EXISTS media_storage_key, "
        "DROP COLUMN IF EXISTS media_content_type"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE instagram_save_docs "
        "ADD COLUMN IF NOT EXISTS media_storage_key TEXT, "
        "ADD COLUMN IF NOT EXISTS media_content_type TEXT"
    )
    op.execute(
        """
        UPDATE instagram_save_docs
        SET media_storage_key = media->0->>'storage_key',
            media_content_type = media->0->>'content_type'
        WHERE jsonb_array_length(media) > 0
        """
    )
    op.execute("ALTER TABLE instagram_save_docs DROP COLUMN IF EXISTS media")
