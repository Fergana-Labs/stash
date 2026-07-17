import pytest
from cryptography.fernet import Fernet

from backend.config import (
    parse_auth0_domain,
    parse_cors_origins,
    parse_integration_encryption_key,
    parse_oauth_redirect_uri,
    parse_optional_secret,
    parse_public_url,
    parse_required_when_enabled,
    parse_s3_endpoint,
    parse_s3_setting,
)


def test_parse_cors_origins_trims_empty_values():
    assert parse_cors_origins(" http://localhost:3457, ,https://app.example.com ") == [
        "http://localhost:3457",
        "https://app.example.com",
    ]


def test_parse_cors_origins_rejects_wildcard_with_credentials():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS cannot include"):
        parse_cors_origins("https://app.example.com,*")


def test_parse_cors_origins_require_https_origins_for_managed_auth():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be an HTTPS origin"):
        parse_cors_origins("https://app.example.com,http://localhost:3457", True)


def test_parse_cors_origins_rejects_paths_for_managed_auth():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be an HTTPS origin"):
        parse_cors_origins("https://app.example.com/settings", True)


def test_parse_cors_origins_allows_https_origins_for_managed_auth():
    assert parse_cors_origins("https://app.example.com,https://admin.example.com/", True) == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_parse_public_url_requires_https_origin_for_managed_auth():
    with pytest.raises(RuntimeError, match="PUBLIC_URL must be an HTTPS origin"):
        parse_public_url("http://app.example.com", True)


def test_parse_public_url_allows_local_http_when_managed_auth_is_disabled():
    assert parse_public_url("http://localhost:3457", False) == "http://localhost:3457"


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


def test_parse_integration_encryption_key_requires_key_for_managed_auth(monkeypatch):
    monkeypatch.delenv("INTEGRATIONS_ENCRYPTION_KEY", raising=False)

    with pytest.raises(RuntimeError, match="INTEGRATIONS_ENCRYPTION_KEY must be set"):
        parse_integration_encryption_key(True)


def test_parse_integration_encryption_key_rejects_invalid_configured_key(monkeypatch):
    monkeypatch.setenv("INTEGRATIONS_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(RuntimeError, match="INTEGRATIONS_ENCRYPTION_KEY must be one or more"):
        parse_integration_encryption_key(False)


def test_parse_integration_encryption_key_normalizes_valid_keyring(monkeypatch):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATIONS_ENCRYPTION_KEY", f" {new_key}, {old_key} ")

    assert parse_integration_encryption_key(True) == f"{new_key},{old_key}"


@pytest.mark.parametrize(
    "name",
    ["S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"],
)
def test_parse_s3_settings_require_complete_storage_for_managed_auth(monkeypatch, name):
    monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match=f"{name} must be set"):
        if name == "S3_ENDPOINT":
            parse_s3_endpoint(True)
        else:
            parse_s3_setting(name, True)


def test_parse_s3_endpoint_requires_https_origin_for_managed_auth(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "http://minio:9000")

    with pytest.raises(RuntimeError, match="S3_ENDPOINT must be an HTTPS origin"):
        parse_s3_endpoint(True)


def test_parse_s3_endpoint_allows_local_http_when_managed_auth_is_disabled(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "http://minio:9000")

    assert parse_s3_endpoint(False) == "http://minio:9000"


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://localhost:3456/api/v1/integrations/jira/callback",
        "https://api.example.com/api/v1/integrations/jira/callback;param",
        "https://api.example.com/api/v1/integrations/jira/callback?code=bad",
        "https://api.example.com/api/v1/integrations/jira/callback#fragment",
        "not-a-url",
    ],
)
def test_parse_oauth_redirect_uri_requires_https_callback_for_managed_auth(
    monkeypatch, redirect_uri
):
    monkeypatch.setenv("JIRA_OAUTH_REDIRECT_URI", redirect_uri)

    with pytest.raises(RuntimeError, match="JIRA_OAUTH_REDIRECT_URI must be an HTTPS URL"):
        parse_oauth_redirect_uri("JIRA_OAUTH_REDIRECT_URI", True)


def test_parse_oauth_redirect_uri_allows_https_callback_path_for_managed_auth(monkeypatch):
    redirect_uri = "https://api.example.com/api/v1/integrations/jira/callback"
    monkeypatch.setenv("JIRA_OAUTH_REDIRECT_URI", redirect_uri)

    assert parse_oauth_redirect_uri("JIRA_OAUTH_REDIRECT_URI", True) == redirect_uri


def test_parse_oauth_redirect_uri_allows_local_http_when_managed_auth_is_disabled(monkeypatch):
    redirect_uri = "http://localhost:3456/api/v1/integrations/jira/callback"
    monkeypatch.setenv("JIRA_OAUTH_REDIRECT_URI", redirect_uri)

    assert parse_oauth_redirect_uri("JIRA_OAUTH_REDIRECT_URI", False) == redirect_uri


def test_parse_oauth_redirect_uri_allows_unset_provider_for_managed_auth(monkeypatch):
    monkeypatch.delenv("JIRA_OAUTH_REDIRECT_URI", raising=False)

    assert parse_oauth_redirect_uri("JIRA_OAUTH_REDIRECT_URI", True) is None


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


def test_parse_auth0_domain_skips_format_check_when_disabled(monkeypatch):
    """A leftover scheme-prefixed AUTH0_DOMAIN must not brick a self-hosted
    boot — the value is never used when AUTH0_ENABLED=false."""
    monkeypatch.setenv("AUTH0_DOMAIN", "https://tenant.example.com")

    assert parse_auth0_domain(False) == "https://tenant.example.com"


def test_every_oauth_redirect_uri_setting_uses_the_managed_validator():
    """A provider wired through raw os.getenv lets an http:// or query-bearing
    callback boot cleanly in managed mode (the Gmail regression this pins), so
    every *_OAUTH_REDIRECT_URI must go through parse_oauth_redirect_uri."""
    import inspect
    import re

    from backend.config import Settings

    source = inspect.getsource(Settings)
    assignments = re.findall(r"(\w+_OAUTH_REDIRECT_URI): str \| None = (\w+)", source)
    names = {name for name, _ in assignments}
    assert {"GMAIL_OAUTH_REDIRECT_URI"} <= names
    assert len(assignments) >= 8
    for name, parser in assignments:
        assert parser == "parse_oauth_redirect_uri", name
