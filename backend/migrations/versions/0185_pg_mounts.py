"""External read-only Postgres mounts, queryable through stash sql.

A mount names a customer-side database (e.g. a Supabase project) whose
tables materialize into the per-query DuckDB alongside the scope's native
tables. The DSN is Fernet-encrypted with the integrations keyring, same as
OAuth tokens.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pg_mounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            dsn_encrypted bytea NOT NULL,
            remote_schema text NOT NULL DEFAULT 'public',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (owner_user_id, name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE pg_mounts")
