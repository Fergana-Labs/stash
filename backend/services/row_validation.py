"""Validate a row's data dict against a table's column schema.

Used by every row write path (create, batch create, update, batch update) so
bad input is rejected at the API boundary instead of landing silently in JSONB
and surfacing later as confusing downstream failures.
"""

import re
from datetime import date, datetime


class RowValidationError(ValueError):
    """Raised with a list of human-readable error strings."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def validate_row_data(
    columns: list[dict],
    data: dict,
    *,
    partial: bool = False,
) -> dict:
    """Validate and normalise `data` against `columns`.

    - Unknown keys are rejected.
    - In full mode, required columns without a default must be present.
    - Values are coerced where unambiguous (numeric strings, bool-ish strings).
    - Defaults are applied for missing non-required columns (full mode only).

    Returns the normalised data dict. Raises RowValidationError on any failure.
    """
    by_id = {c["id"]: c for c in columns}
    name_to_id = {c["name"]: c["id"] for c in columns}
    errors: list[str] = []
    normalised: dict = {}

    for key, value in data.items():
        col = by_id.get(key) or by_id.get(name_to_id.get(key, ""))
        if col is None:
            errors.append(_unknown_key_error(key, columns))
            continue
        try:
            normalised[col["id"]] = _coerce(col, value)
        except ValueError as exc:
            errors.append(f"{col['name']}: {exc}")

    if not partial:
        for col in columns:
            if col["id"] in normalised:
                continue
            if col.get("required"):
                if col.get("default") is not None:
                    normalised[col["id"]] = col["default"]
                else:
                    errors.append(f"{col['name']}: required")
            elif col.get("default") is not None:
                normalised[col["id"]] = col["default"]

    if errors:
        raise RowValidationError(errors)
    return normalised


def _unknown_key_error(key: str, columns: list[dict]) -> str:
    valid = ", ".join(c["name"] for c in columns) or "(none)"
    return f"unknown column '{key}'. Valid columns: {valid}"


def _coerce(col: dict, value):
    """Coerce `value` to match `col['type']`. Returns the normalised value.

    None passes through for any column — NULL is always acceptable at the
    row-data level; required-ness is enforced separately.
    """
    if value is None:
        return None

    ctype = col["type"]

    if ctype == "text":
        return str(value)

    if ctype == "number":
        if isinstance(value, bool):
            raise ValueError("expected number, got boolean")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                raise ValueError(f"expected number, got {value!r}")
        raise ValueError(f"expected number, got {type(value).__name__}")

    if ctype == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "1"):
                return True
            if lowered in ("false", "no", "0"):
                return False
        raise ValueError(f"expected boolean, got {value!r}")

    if ctype == "date":
        return _coerce_date(value, with_time=False)

    if ctype == "datetime":
        return _coerce_date(value, with_time=True)

    if ctype == "url":
        if not isinstance(value, str) or not _URL_RE.match(value):
            raise ValueError(f"expected url (http/https), got {value!r}")
        return value

    if ctype == "email":
        if not isinstance(value, str) or not _EMAIL_RE.match(value):
            raise ValueError(f"expected email, got {value!r}")
        return value

    if ctype == "select":
        options = col.get("options") or []
        if options and value not in options:
            raise ValueError(f"expected one of {options}, got {value!r}")
        return value

    if ctype == "multiselect":
        if not isinstance(value, list):
            raise ValueError(f"expected list, got {type(value).__name__}")
        options = col.get("options") or []
        if options:
            bad = [v for v in value if v not in options]
            if bad:
                raise ValueError(f"values not in options {options}: {bad}")
        return value

    if ctype == "json":
        return value

    raise ValueError(f"unknown column type {ctype!r}")


def _coerce_date(value, *, with_time: bool):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"expected ISO {'datetime' if with_time else 'date'}, got {value!r}")
        return parsed.isoformat() if with_time else parsed.date().isoformat()
    raise ValueError(f"expected ISO {'datetime' if with_time else 'date'}, got {type(value).__name__}")
