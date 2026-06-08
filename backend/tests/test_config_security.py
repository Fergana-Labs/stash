import pytest

from backend.config import parse_cors_origins, parse_optional_secret


def test_parse_cors_origins_trims_empty_values():
    assert parse_cors_origins(" http://localhost:3457, ,https://app.example.com ") == [
        "http://localhost:3457",
        "https://app.example.com",
    ]


def test_parse_cors_origins_rejects_wildcard_with_credentials():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS cannot include"):
        parse_cors_origins("https://app.example.com,*")


def test_parse_optional_secret_rejects_short_configured_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "short")

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD must be at least 32 characters"):
        parse_optional_secret("ADMIN_PASSWORD")


def test_parse_optional_secret_allows_unset_secret(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    assert parse_optional_secret("ADMIN_PASSWORD") is None
