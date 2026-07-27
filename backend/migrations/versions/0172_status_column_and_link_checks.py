"""Broken-link checking: a Status column plus a per-row last-checked stamp.

`link_checked_at` is what stops the checker re-probing the same URLs every
sweep and never reaching the tail of a large library. It lives on table_rows
rather than in the Status cell so an inconclusive result (a 403, a timeout)
can still advance the queue without writing a verdict.

Existing bookmarks tables get the Status column appended, with no value —
absent means "not checked yet", which is distinct from OK.
"""

import json
import secrets

from alembic import op

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None

STATUS_COLUMN = {"name": "Status", "type": "select", "options": ["OK", "Broken"], "width": 100}


def upgrade() -> None:
    op.execute("ALTER TABLE table_rows ADD COLUMN IF NOT EXISTS link_checked_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_table_rows_link_checked "
        "ON table_rows(table_id, link_checked_at NULLS FIRST)"
    )

    conn = op.get_bind()
    tables = conn.exec_driver_sql(
        "SELECT id, columns FROM tables WHERE mini_program = 'bookmarks'"
    ).fetchall()
    for table_id, columns in tables:
        columns = columns if isinstance(columns, list) else json.loads(columns)
        if any(c["name"] == "Status" for c in columns):
            continue
        order = max((c.get("order", 0) for c in columns), default=-1) + 1
        columns.append({**STATUS_COLUMN, "id": f"col_{secrets.token_hex(6)}", "order": order})
        conn.exec_driver_sql(
            "UPDATE tables SET columns = $1::jsonb WHERE id = $2",
            (json.dumps(columns), table_id),
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_table_rows_link_checked")
    op.execute("ALTER TABLE table_rows DROP COLUMN IF EXISTS link_checked_at")
