import pytest

from backend.config import parse_cors_origins


def test_parse_cors_origins_trims_empty_values():
    assert parse_cors_origins(" http://localhost:3457, ,https://app.example.com ") == [
        "http://localhost:3457",
        "https://app.example.com",
    ]


def test_parse_cors_origins_rejects_wildcard_with_credentials():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS cannot include"):
        parse_cors_origins("https://app.example.com,*")
