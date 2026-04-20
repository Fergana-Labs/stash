"""Unit tests for row data validation."""

import pytest

from backend.services.row_validation import RowValidationError, validate_row_data


def _col(name, type_, **kw):
    return {"id": f"col_{name}", "name": name, "type": type_, **kw}


def test_happy_path_text_and_number():
    cols = [_col("title", "text"), _col("count", "number")]
    out = validate_row_data(cols, {"title": "hello", "count": 3})
    assert out == {"col_title": "hello", "col_count": 3.0}


def test_accepts_column_ids_directly():
    cols = [_col("title", "text")]
    out = validate_row_data(cols, {"col_title": "x"})
    assert out == {"col_title": "x"}


def test_unknown_key_rejected_with_valid_column_list():
    cols = [_col("title", "text"), _col("kind", "text")]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {"titel": "typo"})
    assert any("titel" in e and "title" in e and "kind" in e for e in ei.value.errors)


def test_required_missing_rejected():
    cols = [_col("title", "text", required=True)]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {})
    assert any("title" in e and "required" in e for e in ei.value.errors)


def test_required_with_default_uses_default():
    cols = [_col("status", "text", required=True, default="new")]
    out = validate_row_data(cols, {})
    assert out == {"col_status": "new"}


def test_partial_mode_skips_required_check():
    cols = [_col("title", "text", required=True), _col("kind", "text")]
    out = validate_row_data(cols, {"kind": "a"}, partial=True)
    assert out == {"col_kind": "a"}


def test_number_rejects_non_numeric_string():
    cols = [_col("n", "number")]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {"n": "abc"})
    assert any("number" in e for e in ei.value.errors)


def test_number_coerces_numeric_string():
    cols = [_col("n", "number")]
    out = validate_row_data(cols, {"n": "42.5"})
    assert out == {"col_n": 42.5}


def test_boolean_accepts_string_forms():
    cols = [_col("b", "boolean")]
    assert validate_row_data(cols, {"b": "true"}) == {"col_b": True}
    assert validate_row_data(cols, {"b": "no"}) == {"col_b": False}


def test_select_rejects_value_not_in_options():
    cols = [_col("status", "select", options=["a", "b"])]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {"status": "c"})
    assert any("['a', 'b']" in e for e in ei.value.errors)


def test_multiselect_rejects_non_list():
    cols = [_col("tags", "multiselect", options=["x", "y"])]
    with pytest.raises(RowValidationError):
        validate_row_data(cols, {"tags": "x"})


def test_multiselect_rejects_bad_values():
    cols = [_col("tags", "multiselect", options=["x", "y"])]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {"tags": ["x", "z"]})
    assert any("z" in e for e in ei.value.errors)


def test_url_and_email_validation():
    cols = [_col("u", "url"), _col("e", "email")]
    with pytest.raises(RowValidationError):
        validate_row_data(cols, {"u": "not-a-url", "e": "bad"})
    out = validate_row_data(cols, {"u": "https://x.com", "e": "a@b.co"})
    assert out == {"col_u": "https://x.com", "col_e": "a@b.co"}


def test_date_parses_iso():
    cols = [_col("d", "date")]
    assert validate_row_data(cols, {"d": "2026-04-19"}) == {"col_d": "2026-04-19"}


def test_date_rejects_garbage():
    cols = [_col("d", "date")]
    with pytest.raises(RowValidationError):
        validate_row_data(cols, {"d": "yesterday"})


def test_multiple_errors_collected_in_one_pass():
    cols = [
        _col("title", "text", required=True),
        _col("count", "number"),
        _col("status", "select", options=["a"]),
    ]
    with pytest.raises(RowValidationError) as ei:
        validate_row_data(cols, {"count": "nope", "status": "bad"})
    # required + bad number + bad select = 3 errors
    assert len(ei.value.errors) == 3


def test_null_passes_through():
    cols = [_col("title", "text"), _col("count", "number")]
    out = validate_row_data(cols, {"title": None, "count": None})
    assert out == {"col_title": None, "col_count": None}


def test_default_applied_for_non_required_missing():
    cols = [_col("kind", "text", default="note")]
    out = validate_row_data(cols, {})
    assert out == {"col_kind": "note"}
