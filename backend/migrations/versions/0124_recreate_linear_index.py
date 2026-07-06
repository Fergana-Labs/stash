"""Recreate linear_index: production never got it.

0116_linear_source collided with another migration that was also numbered 0116
(later renumbered to 0117 in #659). Production had already recorded revision
0116 when the collision was resolved, so alembic skipped the Linear DDL and
`linear_index` was never created there — the Linear source has been broken in
production since launch.

Databases migrated after the renumber fix DO have the table (their 0116 ran),
so this drops and recreates it for one deterministic outcome everywhere. The
table is an index-only cache rebuilt from Linear on the next sync; dropping it
loses nothing durable. The shape matches the other post-user-scope-collapse
index tables (owner_user_id instead of workspace_id, FK to user_sources).

Revision ID: 0124
Revises: 0123
"""

from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linear_index")
    # No extra (source_id, path) index: the UNIQUE constraint already provides
    # the btree the upsert's ON CONFLICT and lookups use.
    op.execute("""
        CREATE TABLE linear_index (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id           uuid NOT NULL REFERENCES user_sources(id) ON DELETE CASCADE,
            path                text NOT NULL,
            name                text NOT NULL,
            kind                text NOT NULL DEFAULT 'issue',
            external_ref        text,
            external_updated_at timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            deleted_at          timestamptz,
            UNIQUE (source_id, path)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linear_index")
