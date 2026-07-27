"""Adopt existing Bookmarks tables into the bookmarks mini program.

Users who clipped before mini programs existed have a plain "Bookmarks" table
in their Clips folder. This carries them forward in one shot: stamp the slug,
append the Summary and Topics columns, seed the views and enrichment config,
and mark every existing row stale so the enrichment sweep backfills the
library rather than only enriching things saved from now on.

If an owner has multiple historical Bookmarks tables, the oldest is the
canonical library. The others remain ordinary tables: the mini-program index
allows exactly one Bookmarks app per owner, and merging user data here would
be destructive.

Column ids are generated here the same way table_service generates them, so
the enrichment config and views can reference them immediately.
"""

import json
import secrets

from alembic import op

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None

NEW_COLUMNS = [
    {"name": "Summary", "type": "text", "width": 320},
    {"name": "Topics", "type": "multiselect", "options": []},
]


def _column_id() -> str:
    return f"col_{secrets.token_hex(6)}"


def upgrade() -> None:
    conn = op.get_bind()
    tables = conn.exec_driver_sql(
        """
        SELECT id, columns
        FROM (
            SELECT t.id, t.columns,
                   ROW_NUMBER() OVER (
                       PARTITION BY t.owner_user_id
                       ORDER BY t.created_at, t.id
                   ) AS owner_rank
            FROM tables t
            JOIN folders f ON f.id = t.folder_id
            WHERE t.name = 'Bookmarks'
              AND f.name = 'Clips'
              AND f.parent_folder_id IS NULL
              AND t.mini_program IS NULL
        ) candidates
        WHERE owner_rank = 1
        """
    ).fetchall()

    for table_id, columns in tables:
        columns = columns if isinstance(columns, list) else json.loads(columns)
        by_name = {c["name"]: c["id"] for c in columns}

        order = max((c.get("order", 0) for c in columns), default=-1)
        for spec in NEW_COLUMNS:
            if spec["name"] in by_name:
                continue
            order += 1
            column = {**spec, "id": _column_id(), "order": order}
            column.setdefault("width", 180)
            columns.append(column)
            by_name[spec["name"]] = column["id"]

        enrichment = {
            "enabled": True,
            "context_columns": [by_name[n] for n in ("Title", "Site", "URL") if n in by_name],
            "page_column": by_name.get("Clip"),
            "targets": [
                {
                    "column": by_name["Summary"],
                    "kind": "summary",
                    "instruction": (
                        "Two sentences: what this is, and why someone who saved "
                        "it would come back to it. No preamble, no 'This article'."
                    ),
                },
                {"column": by_name["Topics"], "kind": "labels", "max": 2},
            ],
        }
        views = [
            {"id": "view_seed_0", "name": "Recent", "layout": "cards"},
            {"id": "view_seed_1", "name": "By topic", "layout": "cards"},
            {"id": "view_seed_2", "name": "All rows", "layout": "table"},
        ]
        if "Saved" in by_name:
            views[0]["sort_by"] = by_name["Saved"]
            views[0]["sort_order"] = "desc"

        embed_columns = [by_name[n] for n in ("Title", "Summary", "Topics", "Site") if n in by_name]
        conn.exec_driver_sql(
            "UPDATE tables SET mini_program = 'bookmarks', columns = $1::jsonb, "
            "  enrichment_config = $2::jsonb, views = $3::jsonb, "
            "  embedding_config = $4::jsonb "
            "WHERE id = $5",
            (
                json.dumps(columns),
                json.dumps(enrichment),
                json.dumps(views),
                json.dumps({"enabled": True, "columns": embed_columns}),
                table_id,
            ),
        )
        # Backfill: every existing bookmark gets a summary and topics.
        conn.exec_driver_sql(
            "UPDATE table_rows SET enrich_stale = TRUE WHERE table_id = $1", (table_id,)
        )


def downgrade() -> None:
    # The added columns and derived cells are left in place — dropping them
    # would discard enrichment the user can see. Only the app identity goes.
    op.execute(
        "UPDATE tables SET mini_program = NULL, enrichment_config = NULL "
        "WHERE mini_program = 'bookmarks'"
    )
