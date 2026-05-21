"""Notion database → Stash table.

Schema mapping: each Notion property becomes a Stash column. Property
types that have a 1:1 analog (number, checkbox, url, email, select,
multi_select, date) map directly; everything else flattens to text.

Query: pages through `POST /v1/databases/{id}/query` 100 entries at a
time, no filter, no sort — we always import the full set. Views,
filters, and sorts don't survive (out of scope for v1).

Per-property value extraction handles each Notion type's quirky
shape: title is rich_text inside a `title` array, formula returns
its inner result type, rollups can return any of several shapes, etc.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from uuid import UUID

import httpx

from ....services import table_service

logger = logging.getLogger(__name__)

NOTION_DATABASE_URL = "https://api.notion.com/v1/databases/{database_id}"
NOTION_QUERY_URL = "https://api.notion.com/v1/databases/{database_id}/query"

# Hard cap so a runaway 100k-row database doesn't lock up a worker.
MAX_ROWS_PER_IMPORT = 5000


def _extract_db_title(db_meta: dict) -> str:
    title_runs = db_meta.get("title", []) or []
    text = "".join(r.get("plain_text", "") for r in title_runs).strip()
    return text or "Imported from Notion database"


def _notion_prop_to_column(prop_name: str, prop_def: dict) -> dict:
    """Map one Notion property definition to a Stash column descriptor.

    The `options` field on select/multi-select columns lists allowed
    values up-front so the UI knows the choice set; new values that
    appear in row data are still accepted (Stash columns are tolerant).
    """
    notion_type = prop_def.get("type")
    col_id = f"col_{secrets.token_hex(6)}"
    base = {"id": col_id, "name": prop_name}

    if notion_type in ("title", "rich_text"):
        return {**base, "type": "text"}
    if notion_type == "number":
        return {**base, "type": "number"}
    if notion_type == "checkbox":
        return {**base, "type": "boolean"}
    if notion_type == "url":
        return {**base, "type": "url"}
    if notion_type == "email":
        return {**base, "type": "email"}
    if notion_type in ("select", "status"):
        opts = (prop_def.get(notion_type) or {}).get("options") or []
        return {
            **base,
            "type": "select",
            "options": [o.get("name", "") for o in opts if o.get("name")],
        }
    if notion_type == "multi_select":
        opts = (prop_def.get("multi_select") or {}).get("options") or []
        return {
            **base,
            "type": "multiselect",
            "options": [o.get("name", "") for o in opts if o.get("name")],
        }
    if notion_type in ("date", "created_time", "last_edited_time"):
        return {**base, "type": "datetime"}
    # phone_number, people, files, relation, formula, rollup,
    # created_by, last_edited_by, unique_id — flatten to text.
    return {**base, "type": "text"}


def _notion_value_to_stash(prop_value: dict) -> Any:
    """Pull a single property value out of Notion's typed envelope."""
    if not prop_value:
        return ""
    notion_type = prop_value.get("type")
    v = prop_value.get(notion_type)

    if notion_type == "title":
        return "".join(r.get("plain_text", "") for r in (v or []))
    if notion_type == "rich_text":
        return "".join(r.get("plain_text", "") for r in (v or []))
    if notion_type == "number":
        return v
    if notion_type == "checkbox":
        return bool(v)
    if notion_type == "url":
        return v or ""
    if notion_type == "email":
        return v or ""
    if notion_type == "phone_number":
        return v or ""
    if notion_type == "select":
        return (v or {}).get("name", "") if v else ""
    if notion_type == "status":
        return (v or {}).get("name", "") if v else ""
    if notion_type == "multi_select":
        return [opt.get("name", "") for opt in (v or [])]
    if notion_type == "date":
        # Notion dates can be (start, end). Take start; end is dropped
        # (v1 limitation — documented).
        return (v or {}).get("start") if v else None
    if notion_type == "people":
        return ", ".join(p.get("name", "") for p in (v or []) if p.get("name"))
    if notion_type == "files":
        urls = []
        for f in v or []:
            file_obj = f.get("file") or f.get("external") or {}
            url = file_obj.get("url")
            if url:
                urls.append(url)
        return ", ".join(urls)
    if notion_type == "relation":
        return ", ".join(r.get("id", "") for r in (v or []) if r.get("id"))
    if notion_type == "formula":
        # formula = { type: "string"|"number"|"boolean"|"date", <type>: ... }
        inner = (v or {}).get("type")
        return _stringify_formula_or_rollup((v or {}).get(inner, ""))
    if notion_type == "rollup":
        inner = (v or {}).get("type")
        return _stringify_formula_or_rollup((v or {}).get(inner, ""))
    if notion_type in ("created_time", "last_edited_time"):
        return v
    if notion_type in ("created_by", "last_edited_by"):
        return (v or {}).get("name", "") if v else ""
    if notion_type == "unique_id":
        prefix = (v or {}).get("prefix") or ""
        number = (v or {}).get("number")
        return f"{prefix}{number}" if number is not None else ""
    # Unknown types fall through to an empty string rather than a
    # cryptic object dump.
    return ""


def _stringify_formula_or_rollup(value: Any) -> str:
    """Formula / rollup values can be lists, dates, or scalars."""
    if value is None:
        return ""
    if isinstance(value, dict):
        # date-shaped formula result
        if "start" in value:
            return value.get("start") or ""
        return ""
    if isinstance(value, list):
        return ", ".join(_stringify_formula_or_rollup(v) for v in value if v)
    return str(value)


async def import_database(
    client: httpx.AsyncClient,
    user_id: UUID,
    workspace_id: UUID,
    database_id: str,
    folder_id: UUID | None,
) -> dict:
    db_resp = await client.get(NOTION_DATABASE_URL.format(database_id=database_id))
    if db_resp.status_code == 404:
        raise RuntimeError(
            f"Notion database {database_id} not found — share it with the connected integration first"
        )
    db_resp.raise_for_status()
    db_meta = db_resp.json()
    title = _extract_db_title(db_meta)

    notion_props = db_meta.get("properties", {}) or {}
    # Notion property iteration order isn't guaranteed; sort for stability.
    columns: list[dict] = []
    prop_id_to_col_id: dict[str, str] = {}
    for prop_name in sorted(notion_props.keys()):
        prop_def = notion_props[prop_name]
        col = _notion_prop_to_column(prop_name, prop_def)
        columns.append(col)
        prop_id_to_col_id[prop_name] = col["id"]

    table = await table_service.create_table(
        workspace_id=workspace_id,
        name=title,
        description=f"Imported from Notion database ({database_id})",
        columns=columns,
        created_by=user_id,
    )

    rows: list[dict] = []
    cursor: str | None = None
    truncated = False
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = await client.post(
            NOTION_QUERY_URL.format(database_id=database_id),
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
        for entry in payload.get("results", []):
            if len(rows) >= MAX_ROWS_PER_IMPORT:
                # Bail at the cap instead of raising — the user gets the
                # first N rows in a usable table with a clear note in the
                # description rather than an empty stub + a confusing error.
                truncated = True
                break
            entry_props = entry.get("properties", {}) or {}
            row: dict[str, Any] = {}
            for prop_name, col_id in prop_id_to_col_id.items():
                row[col_id] = _notion_value_to_stash(entry_props.get(prop_name) or {})
            rows.append(row)
        if truncated or not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")

    if rows:
        await table_service.create_rows_batch(
            table_id=table["id"],
            rows_data=rows,
            created_by=user_id,
        )

    if truncated:
        await table_service.update_table(
            table_id=table["id"],
            description=(
                f"Imported from Notion database ({database_id}) — "
                f"truncated at {MAX_ROWS_PER_IMPORT} rows"
            ),
            updated_by=user_id,
        )

    return {
        "kind": "table",
        "table_id": str(table["id"]),
        "name": title,
        "row_count": len(rows),
        "column_count": len(columns),
        "truncated": truncated,
    }
