"""Fold X saves into kind folders + make the source navigable.

X saves now live under Bookmarks/ Posts/ Replies/ Articles/ in the VFS (path =
"<Folder>/<tweet id>"). Rename existing flat rows and switch the existing
x_saves sources to the navigable capability so the browse UI shows folders.

Revision ID: 0156
Revises: 0155
"""

from alembic import op

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE x_save_docs SET path =
            CASE kind
                WHEN 'Bookmark' THEN 'Bookmarks/'
                WHEN 'Post' THEN 'Posts/'
                WHEN 'Reply' THEN 'Replies/'
                WHEN 'Article' THEN 'Articles/'
                ELSE 'Other/'
            END || path
        WHERE path NOT LIKE '%/%'
        """
    )
    op.execute("UPDATE user_sources SET capability = 'navigable' WHERE source_type = 'x_saves'")


def downgrade() -> None:
    op.execute("UPDATE x_save_docs SET path = split_part(path, '/', 2) WHERE path LIKE '%/%'")
    op.execute("UPDATE user_sources SET capability = 'searchable' WHERE source_type = 'x_saves'")
