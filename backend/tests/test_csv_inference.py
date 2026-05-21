"""Lock in the shared CSV type-inference + coercion behaviour.

Both /files/{id}/ingest-csv and the Google Sheets importer depend on
these helpers producing identical results, so changes here would break
import parity between the two paths.
"""

import pytest

from backend.services.csv_inference import coerce_value, infer_column_type


class TestInferColumnType:
    def test_empty_samples_default_to_text(self):
        assert infer_column_type([]) == "text"
        assert infer_column_type(["", "", ""]) == "text"

    def test_boolean(self):
        assert infer_column_type(["true", "false", "yes", "no"]) == "boolean"
        assert infer_column_type(["Y", "N", "0", "1"]) == "boolean"

    def test_number_with_currency_commas_percent(self):
        assert infer_column_type(["1", "2.5", "$1,234.50", "-3", "12%"]) == "number"

    def test_date_without_time(self):
        assert infer_column_type(["2026-01-01", "2026-05-21"]) == "date"

    def test_datetime_when_every_value_has_T(self):
        assert (
            infer_column_type(["2026-01-01T10:00:00Z", "2026-05-21T00:00:00+00:00"]) == "datetime"
        )

    def test_mixed_falls_back_to_text(self):
        assert infer_column_type(["1", "hello"]) == "text"

    def test_empty_strings_dont_affect_inference(self):
        assert infer_column_type(["", "42", "", "7"]) == "number"


class TestCoerceValue:
    def test_empty_becomes_none(self):
        assert coerce_value("", "text") is None
        assert coerce_value("", "number") is None

    def test_boolean(self):
        assert coerce_value("yes", "boolean") is True
        assert coerce_value("Y", "boolean") is True
        assert coerce_value("1", "boolean") is True
        assert coerce_value("no", "boolean") is False
        assert coerce_value("0", "boolean") is False

    def test_number_strips_formatting(self):
        assert coerce_value("$1,234.50", "number") == 1234.5
        assert coerce_value("12%", "number") == 12
        assert coerce_value("-3", "number") == -3

    def test_number_returns_int_when_integer_valued(self):
        assert coerce_value("42", "number") == 42
        assert isinstance(coerce_value("42", "number"), int)

    def test_number_falls_through_on_unparseable(self):
        # Garbage strings pass through rather than crashing the import.
        assert coerce_value("not-a-number", "number") == "not-a-number"

    def test_date_normalises_to_isoformat(self):
        assert coerce_value("2026-05-21", "date") == "2026-05-21T00:00:00"

    def test_datetime_with_z_suffix(self):
        # Z gets rewritten to +00:00 so Python's fromisoformat can parse it.
        assert coerce_value("2026-05-21T10:00:00Z", "datetime") == "2026-05-21T10:00:00+00:00"

    def test_text_passes_through(self):
        assert coerce_value("hello", "text") == "hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
