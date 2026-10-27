"""Require a review of the exact shared page before customer publication.

Revision ID: 0254
Revises: 0253
"""

from alembic import op

revision = "0254"
down_revision = "0253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No backfill: existing pages remain available to their developer, but are
    # quarantined from customer retrieval until explicitly reviewed.
    op.execute("""
        CREATE TABLE shared_wiki_reviews (
            page_id uuid PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            folder_id uuid NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
            policy_version text NOT NULL,
            name text NOT NULL,
            content_markdown text NOT NULL,
            reviewed_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ON shared_wiki_reviews (workspace_id)")
    op.execute("""
        CREATE TABLE shared_wiki_originals (
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            page_id uuid NOT NULL,
            fingerprint text NOT NULL,
            original jsonb NOT NULL,
            archived_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id,page_id,fingerprint)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE shared_wiki_originals")
    op.execute("DROP TABLE shared_wiki_reviews")
