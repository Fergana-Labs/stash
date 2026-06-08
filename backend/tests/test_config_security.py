import pytest

from backend.config import (
    parse_auth0_domain,
    parse_cors_origins,
    parse_optional_secret,
    parse_required_when_enabled,
)


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


def test_parse_required_when_enabled_requires_managed_secret(monkeypatch):
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="AUTH0_AUDIENCE must be set"):
        parse_required_when_enabled("AUTH0_AUDIENCE", True, "AUTH0_ENABLED")


def test_parse_required_when_enabled_allows_unset_when_disabled(monkeypatch):
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)

    assert parse_required_when_enabled("AUTH0_AUDIENCE", False, "AUTH0_ENABLED") is None


@pytest.mark.parametrize(
    "domain",
    [
        "https://tenant.example.com",
        "tenant.example.com/",
        "tenant.example.com/path",
        "tenant example.com",
    ],
)
def test_parse_auth0_domain_rejects_non_hostname_values(monkeypatch, domain):
    monkeypatch.setenv("AUTH0_DOMAIN", domain)

    with pytest.raises(RuntimeError, match="AUTH0_DOMAIN must be a hostname"):
        parse_auth0_domain(True)


def test_parse_auth0_domain_accepts_hostname(monkeypatch):
    monkeypatch.setenv("AUTH0_DOMAIN", "tenant.example.com")

    assert parse_auth0_domain(True) == "tenant.example.com"
