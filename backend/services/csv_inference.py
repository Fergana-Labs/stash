"""Column-type inference and value coercion for CSV-like imports.

Shared between the file `/ingest-csv` endpoint and the Google Sheets
importer so both code paths produce identically-typed tables when
given the same input data.
"""

from __future__ import annotations

import re
from datetime import datetime

_NUMERIC_RE = re.compile(r"^-?\$?[\d,]+(\.\d+)?%?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$")
_BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "0", "1"}


def infer_column_type(samples: list[str]) -> str:
    """Pick the narrowest fit across the sampled values.

    Promotes upward on any miss: bool → number → date → text. Empty strings
    don't contribute to the decision.
    """
    nonempty = [s for s in samples if s != ""]
    if not nonempty:
        return "text"

    def matches(pred) -> bool:
        return all(pred(s) for s in nonempty)

    if matches(lambda s: s.lower() in _BOOL_VALUES):
        return "boolean"
    if matches(lambda s: bool(_NUMERIC_RE.match(s))):
        return "number"
    if matches(lambda s: bool(_DATE_RE.match(s))):
        if all("T" in s for s in nonempty):
            return "datetime"
        return "date"
    return "text"


def coerce_value(raw: str, col_type: str):
    if raw == "":
        return None
    if col_type == "boolean":
        return raw.lower() in ("true", "yes", "y", "1")
    if col_type == "number":
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            v = float(cleaned)
            return int(v) if v.is_integer() else v
        except ValueError:
            return raw
    if col_type in ("date", "datetime"):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return raw
    return raw
