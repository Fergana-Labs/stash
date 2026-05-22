"""Lock in the cell-to-string conversion for XLSX ingest.

The XLSX importer leans on `_cell_to_str` to feed openpyxl values into
the same `infer_column_type` / `coerce_value` pipeline as CSV cells.
The mapping needs to be exact — integer-valued floats must lose their
`.0` (so they infer as `number`, not `text`), and datetimes must emit
ISO format (so the date regex matches).
"""

from datetime import date, datetime

from backend.services.csv_inference import infer_column_type
from backend.services.xlsx_ingest import _cell_to_str


def test_none_becomes_empty_string():
    assert _cell_to_str(None) == ""


def test_bool_is_lowercased():
    assert _cell_to_str(True) == "true"
    assert _cell_to_str(False) == "false"


def test_integer_valued_float_drops_trailing_zero():
    # Excel stores plain numbers as floats; without the strip, "42.0"
    # would infer as text since the numeric regex tolerates it but the
    # row coercion would force float typing forever.
    assert _cell_to_str(42.0) == "42"
    assert _cell_to_str(0.0) == "0"


def test_real_float_keeps_decimal():
    assert _cell_to_str(2.5) == "2.5"


def test_integer_stays_integer():
    assert _cell_to_str(42) == "42"


def test_datetime_emits_iso():
    s = _cell_to_str(datetime(2026, 5, 21, 10, 0, 0))
    assert s == "2026-05-21T10:00:00"
    # Must round-trip through inference as datetime.
    assert infer_column_type([s]) == "datetime"


def test_date_emits_iso():
    s = _cell_to_str(date(2026, 5, 21))
    assert s == "2026-05-21"
    assert infer_column_type([s]) == "date"
