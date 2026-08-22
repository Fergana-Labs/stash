"""Rename tenants to end users.

The console and the developer API call them "users" — one end user of the
developer's product. Inside the database "users" is taken by Stash accounts,
so the table is end_users and the foreign keys end_user_id; the wire speaks
user_id, the schema end_user_id, and nothing anywhere says tenant.

Mostly a pure rename (Postgres carries indexes and foreign keys across it).
The one data change: each workspace's "Tenant Notepads" folder — a
user-visible name — becomes "User Notepads".

Revision ID: 0195
Revises: 0194
"""

from alembic import op

revision = "0195"
down_revision = "0194"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("sessions", "tenant_id", "end_user_id"),
    ("files", "tenant_id", "end_user_id"),
    ("pages", "tenant_id", "end_user_id"),
    ("user_sources", "tenant_id", "end_user_id"),
    ("workspaces", "tenant_notepads_folder_id", "end_user_notepads_folder_id"),
]

_INDEXES = [
    ("idx_sessions_tenant", "idx_sessions_end_user"),
    ("idx_files_tenant", "idx_files_end_user"),
    ("idx_pages_tenant", "idx_pages_end_user"),
    ("idx_user_sources_tenant", "idx_user_sources_end_user"),
]


def upgrade() -> None:
    op.execute("ALTER TABLE tenants RENAME TO end_users")
    for table, old, new in _COLUMNS:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    for old, new in _INDEXES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")
    op.execute(
        "UPDATE folders SET name = 'User Notepads' "
        "WHERE id IN (SELECT end_user_notepads_folder_id FROM workspaces) "
        "  AND name = 'Tenant Notepads'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE folders SET name = 'Tenant Notepads' "
        "WHERE id IN (SELECT end_user_notepads_folder_id FROM workspaces) "
        "  AND name = 'User Notepads'"
    )
    for old, new in _INDEXES:
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
    for table, old, new in _COLUMNS:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {new} TO {old}")
    op.execute("ALTER TABLE end_users RENAME TO tenants")
