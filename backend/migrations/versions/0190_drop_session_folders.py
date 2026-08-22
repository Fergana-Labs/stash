"""Session folders live on (this migration is now a no-op).

This originally converted keyed session folders into platform end users and
dropped the table. Prod reality vetoed it: session folders are the live write
path for Heavi's backend and for every installed CLI/plugin/extension, and
the conversion required folder owners to be workspace scope users — which
Heavi's account is not. Running it would have deleted their per-customer
grouping unconverted.

The legacy lane stays: folders are honored when clients send them and read by
nothing new. The real cutover (convert, then drop) ships as a future
migration, coordinated with Heavi.

Revision ID: 0190
Revises: 0189
"""

from alembic import op  # noqa: F401 — kept for the migration interface

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
