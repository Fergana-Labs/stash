"""Rename every workspace_id to owner_user_id and drop the workspaces stub.

Second stage of removing "workspace". After 0118 each user owns exactly one
scope, stored 1:1 in the workspaces table — so workspace_id (= workspaces.id)
maps bijectively to the scope's owner (= workspaces.creator_id = users.id).

For every table carrying workspace_id:
- If the table already has an owner_user_id column, workspace_id is redundant —
  drop it.
- Otherwise, rewrite the value from the workspace id to its creator's user id,
  repoint the foreign key from workspaces to users, and rename the column to
  owner_user_id. Column rename automatically carries indexes / unique / primary
  key definitions over to the new name.

Finally drop the now-unreferenced workspaces table.

Revision ID: 0119
Revises: 0118
"""

from alembic import op
from sqlalchemy import text

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None


def _tables_with_column(conn, column: str) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = :col ORDER BY table_name"
        ),
        {"col": column},
    )
    return [r[0] for r in rows]


def _workspaces_fk(conn, table: str) -> str | None:
    """Name of `table`'s foreign key that references the workspaces table."""
    row = conn.execute(
        text(
            "SELECT tc.constraint_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "  AND ccu.table_schema = tc.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_name = :t AND ccu.table_name = 'workspaces' LIMIT 1"
        ),
        {"t": table},
    ).first()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    with_owner = set(_tables_with_column(conn, "owner_user_id"))

    for table in _tables_with_column(conn, "workspace_id"):
        fk = _workspaces_fk(conn, table)

        if table in with_owner:
            # owner_user_id already carries the scope; workspace_id is redundant.
            if fk:
                op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{fk}"')
            op.execute(f"ALTER TABLE {table} DROP COLUMN workspace_id")
            continue

        # Drop the workspaces FK first: the value rewrite below sets the column
        # to a users.id, which the old workspace-referencing FK would reject.
        if fk:
            op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{fk}"')
        op.execute(
            f"UPDATE {table} t SET workspace_id = "
            "(SELECT w.creator_id FROM workspaces w WHERE w.id = t.workspace_id) "
            "WHERE t.workspace_id IS NOT NULL"
        )
        op.execute(f"ALTER TABLE {table} RENAME COLUMN workspace_id TO owner_user_id")
        if fk:
            op.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_owner_user_id_fkey "
                "FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE"
            )

    # Dropping workspace_id from workspace_sources auto-dropped the unique it was
    # part of (workspace_id, owner_user_id, source_type, external_ref). Re-add the
    # owner-scoped one so source upserts (ON CONFLICT) keep working.
    op.execute(
        "ALTER TABLE workspace_sources ADD CONSTRAINT "
        "workspace_sources_owner_user_id_source_type_external_ref_key "
        "UNIQUE (owner_user_id, source_type, external_ref)"
    )

    op.execute("DROP TABLE workspaces")


def downgrade() -> None:
    raise NotImplementedError("Renaming the scope column is one-way.")
