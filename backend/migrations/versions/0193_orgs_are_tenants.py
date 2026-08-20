"""Rename orgs to tenants.

A tenant is one end user of a customer's product: a repair shop for Heavi, or
one person for a shopping chatbot. "Org" implied a company, which excluded half
of what this is for and made the per-person case read as a misuse.

Pure rename — no behaviour change. Postgres carries indexes and foreign keys
across a table rename, so only the names move.

Revision ID: 0193
Revises: 0192
"""

from alembic import op

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("sessions", "org_id", "tenant_id"),
    ("files", "org_id", "tenant_id"),
    ("pages", "org_id", "tenant_id"),
    ("user_sources", "org_id", "tenant_id"),
    ("workspaces", "org_notepads_folder_id", "tenant_notepads_folder_id"),
]

_INDEXES = [
    ("idx_sessions_org", "idx_sessions_tenant"),
    ("idx_files_org", "idx_files_tenant"),
    ("idx_pages_org", "idx_pages_tenant"),
    ("idx_user_sources_org", "idx_user_sources_tenant"),
]


def upgrade() -> None:
    op.execute("ALTER TABLE orgs RENAME TO tenants")
    for table, old, new in _COLUMNS:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    for old, new in _INDEXES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")


def downgrade() -> None:
    for old, new in _INDEXES:
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
    for table, old, new in _COLUMNS:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {new} TO {old}")
    op.execute("ALTER TABLE tenants RENAME TO orgs")
