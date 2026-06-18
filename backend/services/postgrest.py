"""Translate PostgREST/supabase-js query grammar to stash's table query layer.

The data API (`/rest/v1/{table}`) is wire-compatible with `supabase-js` for the
core CRUD/filter surface so agents can vibe-code dashboards against it with code
that's already in their training data. These are pure functions over a table's
column schema — the router does auth, lookup, and the DB calls.

Stash tables store cells in a JSONB `data` column keyed by column-id, so reads
map column *names* (what PostgREST speaks) to ids and back. Anything past the
supported subset raises `UnsupportedQuery` so the router can fail loud with 501
rather than return a silently-wrong answer.
"""

from __future__ import annotations

# Query keys that are not column filters.
RESERVED_PARAMS = {"select", "order", "limit", "offset"}

# PostgREST operator -> stash list_rows operator.
_OP_MAP = {
    "eq": "eq",
    "neq": "neq",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
}


class UnsupportedQuery(Exception):
    """A query uses a real PostgREST feature stash doesn't implement (-> HTTP 501)."""


class BadQuery(Exception):
    """A malformed query (-> HTTP 400)."""


def _name_maps(columns: list[dict]) -> tuple[dict, dict, dict]:
    by_name = {c["name"]: c for c in columns}
    name_to_id = {c["name"]: c["id"] for c in columns}
    id_to_name = {c["id"]: c["name"] for c in columns}
    return by_name, name_to_id, id_to_name


def parse_filters(params: list[tuple[str, str]], columns: list[dict]) -> list[dict]:
    """Turn `?revenue=gt.1000&name=ilike.*acme*` into stash filter dicts.

    Each non-reserved query key is a column filter `col=op.value`.
    """
    by_name, name_to_id, _ = _name_maps(columns)
    filters: list[dict] = []

    for key, raw in params:
        if key in RESERVED_PARAMS:
            continue
        if key in ("and", "or", "not"):
            raise UnsupportedQuery("and/or/not filters are not supported")
        if key not in name_to_id:
            raise BadQuery(f"unknown column '{key}'")

        op, _, value = raw.partition(".")
        if not _:
            raise BadQuery(f"filter '{key}' must be 'op.value' (got {raw!r})")
        if op == "not":
            raise UnsupportedQuery("negated filters (not.) are not supported")

        col = by_name[key]
        col_id = name_to_id[key]

        if op == "is":
            if value.lower() == "null":
                filters.append({"column_id": col_id, "op": "is_empty"})
                continue
            raise UnsupportedQuery("only 'is.null' is supported for the is operator")

        if op in ("like", "ilike"):
            # stash offers case-insensitive substring 'contains'; treat the
            # PostgREST pattern's non-wildcard core as the needle.
            filters.append({"column_id": col_id, "op": "contains", "value": value.strip("*")})
            continue

        if op in ("in", "cs", "cd", "fts", "plfts", "phfts", "wfts"):
            raise UnsupportedQuery(f"the '{op}' operator is not supported")

        if op not in _OP_MAP:
            raise BadQuery(f"unknown operator '{op}'")

        filters.append({"column_id": col_id, "op": _OP_MAP[op], "value": _coerce(col, value)})

    return filters


def parse_select(select: str | None, columns: list[dict]) -> set[str] | None:
    """Return the set of column names to project, or None for all columns."""
    if not select or select.strip() == "*":
        return None
    if "(" in select:
        raise UnsupportedQuery("embedded resource selects (joins) are not supported")

    _, name_to_id, _ = _name_maps(columns)
    wanted: set[str] = set()
    for raw in select.split(","):
        name = raw.strip()
        if name in name_to_id or name in SYSTEM_FIELDS:
            wanted.add(name)
        else:
            raise BadQuery(f"unknown column in select: '{name}'")
    return wanted


def parse_order(order: str | None, columns: list[dict]) -> tuple[str | None, str]:
    """Return (sort_by_column_id, 'asc'|'desc'). Single-column order only."""
    if not order:
        return None, "asc"
    terms = [t.strip() for t in order.split(",") if t.strip()]
    if len(terms) > 1:
        raise UnsupportedQuery("multi-column order is not supported; order by one column")

    _, name_to_id, _ = _name_maps(columns)
    parts = terms[0].split(".")
    name = parts[0]
    if name not in name_to_id:
        raise BadQuery(f"unknown column in order: '{name}'")
    direction = "desc" if "desc" in parts[1:] else "asc"
    return name_to_id[name], direction


SYSTEM_FIELDS = ("id", "created_at", "updated_at")


def row_to_named(row: dict, columns: list[dict], project: set[str] | None) -> dict:
    """Map a stored row (data keyed by col-id) to a flat name-keyed object.

    System fields (id/created_at/updated_at) are added unless a user column
    already claims that name. `project`, when set, filters the output keys.
    """
    _, _, id_to_name = _name_maps(columns)
    data = row.get("data") or {}
    out: dict = {id_to_name.get(col_id, col_id): value for col_id, value in data.items()}

    for field in SYSTEM_FIELDS:
        out.setdefault(field, row.get(field))

    if project is not None:
        out = {k: v for k, v in out.items() if k in project}
    return out


def content_range(offset: int, returned: int, total: int) -> str:
    """PostgREST's Content-Range header value, e.g. '0-24/100' (or '*/0' when empty)."""
    if returned == 0:
        return f"*/{total}"
    return f"{offset}-{offset + returned - 1}/{total}"


def _coerce(col: dict, raw: str):
    """Coerce a query-string filter value to match the column type.

    Numbers must become floats so the query layer compares them numerically;
    everything else stays a string (booleans serialize to 'true'/'false' in
    JSONB, which compares fine as text).
    """
    if col["type"] == "number":
        try:
            return float(raw)
        except ValueError:
            raise BadQuery(f"{col['name']}: expected a number, got {raw!r}")
    return raw
