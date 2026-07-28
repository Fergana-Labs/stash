"""Bring table names in line with pages and folders: unique within a folder.

Pages and folders in the same tree have both had per-folder uniqueness since
0001; tables were given a weaker constraint — UNIQUE(created_by, name) WHERE
workspace_id IS NULL — that covered only non-workspace tables, and the
workspaces removal left its predicate matching nothing. So tables ended up
the one thing in the VFS whose names could silently collide.

That mattered beyond tidiness: agent_runtime.query_table resolves a table by
name and takes the first match ordered by updated_at DESC, so an agent asking
for "Notes" got whichever Notes had been touched most recently — a different
table week to week, with no error.

Existing collisions are renamed rather than rejected, following the " (2)"
convention create_page_unique already uses. The oldest table in a colliding
group keeps the name; the rest get suffixes. Nothing is deleted or merged.
"""

from alembic import op

revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Rename collisions before the index goes on, so this is safe to run
    # against a database that already has duplicates.
    for scope in ("folder_id IS NOT NULL", "folder_id IS NULL"):
        partition = (
            "owner_user_id, folder_id, name" if "NOT NULL" in scope else "owner_user_id, name"
        )
        conn.exec_driver_sql(
            f"""
            WITH ranked AS (
                SELECT id, name,
                       ROW_NUMBER() OVER (
                           PARTITION BY {partition} ORDER BY created_at, id
                       ) AS n
                FROM tables
                WHERE owner_user_id IS NOT NULL AND {scope}
            )
            UPDATE tables t
            SET name = ranked.name || ' (' || ranked.n || ')'
            FROM ranked
            WHERE t.id = ranked.id AND ranked.n > 1
            """
        )

    # A rename can itself collide with an existing "Notes (2)"; loop until the
    # partitions are clean rather than assuming one pass is enough.
    for _ in range(10):
        remaining = conn.exec_driver_sql(
            """
            SELECT count(*) FROM (
                SELECT 1 FROM tables
                WHERE owner_user_id IS NOT NULL
                GROUP BY owner_user_id, folder_id, name HAVING count(*) > 1
            ) d
            """
        ).scalar()
        if not remaining:
            break
        conn.exec_driver_sql(
            """
            WITH ranked AS (
                SELECT id, name,
                       ROW_NUMBER() OVER (
                           PARTITION BY owner_user_id, folder_id, name
                           ORDER BY created_at, id
                       ) AS n
                FROM tables WHERE owner_user_id IS NOT NULL
            )
            UPDATE tables t
            SET name = ranked.name || ' (' || ranked.n || ')'
            FROM ranked
            WHERE t.id = ranked.id AND ranked.n > 1
            """
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tables_unique_in_folder "
        "ON tables(owner_user_id, folder_id, name) WHERE folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tables_unique_at_root "
        "ON tables(owner_user_id, name) WHERE folder_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tables_unique_at_root")
    op.execute("DROP INDEX IF EXISTS idx_tables_unique_in_folder")
