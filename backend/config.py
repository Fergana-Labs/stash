"""Centralised settings loaded from environment variables.

All configuration that the backend touches must be declared here.
Defaults are chosen for local development with the bundled docker-compose.yml.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

MIN_ADMIN_SECRET_LENGTH = 32


def parse_https_origin(name: str, value: str) -> str:
    parsed = urlparse(value)
    has_path = parsed.path not in ("", "/")
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or has_path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(f"{name} must be an HTTPS origin without path, query, or fragment")
    return value.rstrip("/")


def parse_public_url(raw: str, managed_auth_enabled: bool) -> str:
    if managed_auth_enabled:
        return parse_https_origin("PUBLIC_URL", raw)
    return raw


def parse_cors_origins(raw: str, managed_auth_enabled: bool = False) -> list[str]:
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS cannot include '*' when credentialed CORS is enabled")
    if managed_auth_enabled:
        return [parse_https_origin("CORS_ORIGINS", origin) for origin in origins]
    return origins


def parse_optional_secret(name: str, min_length: int = MIN_ADMIN_SECRET_LENGTH) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    if len(value) < min_length:
        raise RuntimeError(f"{name} must be at least {min_length} characters")
    return value


def parse_required_when_enabled(name: str, enabled: bool, enabled_name: str) -> str | None:
    value = os.getenv(name)
    if not enabled:
        return value or None
    if not value:
        raise RuntimeError(f"{name} must be set when {enabled_name}=true")
    return value


def parse_integration_encryption_key(enabled: bool) -> str | None:
    raw = os.getenv("INTEGRATIONS_ENCRYPTION_KEY")
    if not raw:
        if enabled:
            raise RuntimeError("INTEGRATIONS_ENCRYPTION_KEY must be set when AUTH0_ENABLED=true")
        return None

    keys = [key.strip() for key in raw.split(",") if key.strip()]
    if not keys:
        if enabled:
            raise RuntimeError("INTEGRATIONS_ENCRYPTION_KEY must be set when AUTH0_ENABLED=true")
        return None

    try:
        for key in keys:
            Fernet(key.encode())
    except ValueError:
        raise RuntimeError("INTEGRATIONS_ENCRYPTION_KEY must be one or more valid Fernet keys")

    return ",".join(keys)


def parse_auth0_domain(enabled: bool) -> str | None:
    value = parse_required_when_enabled("AUTH0_DOMAIN", enabled, "AUTH0_ENABLED")
    if not value:
        return None
    if "://" in value or "/" in value or any(ch.isspace() for ch in value):
        raise RuntimeError("AUTH0_DOMAIN must be a hostname without scheme, path, or spaces")
    return value


def parse_s3_setting(name: str, managed_auth_enabled: bool) -> str | None:
    value = os.getenv(name)
    if managed_auth_enabled and not value:
        raise RuntimeError(f"{name} must be set when AUTH0_ENABLED=true")
    return value or None


def parse_s3_endpoint(managed_auth_enabled: bool) -> str | None:
    endpoint = parse_s3_setting("S3_ENDPOINT", managed_auth_enabled)
    if managed_auth_enabled and endpoint:
        return parse_https_origin("S3_ENDPOINT", endpoint)
    return endpoint


class Settings:
    # --- Server ---
    PORT: int = int(os.getenv("PORT", "3456"))

    # --- Auth0 (managed deployment only) ---
    # When AUTH0_ENABLED=true, password login/register is disabled and the
    # managed auth0 router is mounted at /api/v1/auth0/. Requires the
    # managed/ directory to be present in the deployment.
    AUTH0_ENABLED: bool = os.getenv("AUTH0_ENABLED", "false").lower() == "true"

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://stash:stash@localhost:5432/stash")
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "20"))

    # --- URLs & CORS ---
    PUBLIC_URL: str = parse_public_url(
        os.getenv("PUBLIC_URL", "http://localhost:3457"), AUTH0_ENABLED
    )
    CORS_ORIGINS: list[str] = parse_cors_origins(
        os.getenv(
            "CORS_ORIGINS", "http://localhost:3457,http://localhost:3456,http://localhost:3000"
        ),
        AUTH0_ENABLED,
    )

    # --- Embeddings ---
    # Provider: "openai", "huggingface", "local", or "auto" (default).
    # Auto-detect: OPENAI_API_KEY → openai, HF_TOKEN → huggingface, else → local.
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "auto")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    EMBEDDING_API_KEY: str | None = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    HF_TOKEN: str | None = os.getenv("HF_TOKEN")
    EMBEDDING_MODEL: str | None = os.getenv("EMBEDDING_MODEL")
    EMBEDDING_DIMS: int = int(os.getenv("EMBEDDING_DIMS", "384"))

    # --- File storage (S3-compatible, e.g. Cloudflare R2) ---
    S3_ENDPOINT: str | None = parse_s3_endpoint(AUTH0_ENABLED)
    S3_BUCKET: str | None = parse_s3_setting("S3_BUCKET", AUTH0_ENABLED)
    S3_ACCESS_KEY: str | None = parse_s3_setting("S3_ACCESS_KEY", AUTH0_ENABLED)
    S3_SECRET_KEY: str | None = parse_s3_setting("S3_SECRET_KEY", AUTH0_ENABLED)
    S3_REGION: str = os.getenv("S3_REGION", "auto")

    AUTH0_DOMAIN: str | None = parse_auth0_domain(AUTH0_ENABLED)
    AUTH0_AUDIENCE: str | None = parse_required_when_enabled(
        "AUTH0_AUDIENCE", AUTH0_ENABLED, "AUTH0_ENABLED"
    )

    # --- Email (Postmark) ---
    POSTMARK_SERVER_TOKEN: str | None = os.getenv("POSTMARK_SERVER_TOKEN")

    # --- Admin ---
    # Shared secret for /api/v1/admin/* endpoints. The www admin page sends
    # this in X-Admin-Token from server-side fetches; never exposed to the
    # browser. Leave unset to disable admin endpoints entirely.
    ADMIN_PASSWORD: str | None = parse_optional_secret("ADMIN_PASSWORD")

    # --- Background tasks (Celery + Redis) ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Linear ---
    LINEAR_API_KEY: str | None = os.getenv("LINEAR_API_KEY") or os.getenv("LINEAR_API_TOKEN")
    LINEAR_API_URL: str = os.getenv("LINEAR_API_URL", "https://api.linear.app/graphql")

    # --- Integrations (OAuth + per-user token storage) ---
    # Comma-separated Fernet keyring for encrypting access/refresh tokens at
    # rest. The first key encrypts new values; later keys decrypt during
    # rotation.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    INTEGRATIONS_ENCRYPTION_KEY: str | None = parse_integration_encryption_key(AUTH0_ENABLED)

    GOOGLE_OAUTH_CLIENT_ID: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URI: str | None = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")

    GITHUB_OAUTH_CLIENT_ID: str | None = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    GITHUB_OAUTH_CLIENT_SECRET: str | None = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
    GITHUB_OAUTH_REDIRECT_URI: str | None = os.getenv("GITHUB_OAUTH_REDIRECT_URI")

    NOTION_OAUTH_CLIENT_ID: str | None = os.getenv("NOTION_OAUTH_CLIENT_ID")
    NOTION_OAUTH_CLIENT_SECRET: str | None = os.getenv("NOTION_OAUTH_CLIENT_SECRET")
    NOTION_OAUTH_REDIRECT_URI: str | None = os.getenv("NOTION_OAUTH_REDIRECT_URI")

    JIRA_OAUTH_CLIENT_ID: str | None = os.getenv("JIRA_OAUTH_CLIENT_ID")
    JIRA_OAUTH_CLIENT_SECRET: str | None = os.getenv("JIRA_OAUTH_CLIENT_SECRET")
    JIRA_OAUTH_REDIRECT_URI: str | None = os.getenv("JIRA_OAUTH_REDIRECT_URI")

    ASANA_OAUTH_CLIENT_ID: str | None = os.getenv("ASANA_OAUTH_CLIENT_ID")
    ASANA_OAUTH_CLIENT_SECRET: str | None = os.getenv("ASANA_OAUTH_CLIENT_SECRET")
    ASANA_OAUTH_REDIRECT_URI: str | None = os.getenv("ASANA_OAUTH_REDIRECT_URI")

    SLACK_OAUTH_CLIENT_ID: str | None = os.getenv("SLACK_OAUTH_CLIENT_ID")
    SLACK_OAUTH_CLIENT_SECRET: str | None = os.getenv("SLACK_OAUTH_CLIENT_SECRET")
    SLACK_OAUTH_REDIRECT_URI: str | None = os.getenv("SLACK_OAUTH_REDIRECT_URI")
    # Verifies inbound Events API webhook signatures (X-Slack-Signature).
    SLACK_SIGNING_SECRET: str | None = os.getenv("SLACK_SIGNING_SECRET")

    # Granola connects through its official MCP server over OAuth 2.0 with
    # Dynamic Client Registration + PKCE — no pre-shared client_id/secret. We
    # only need the MCP endpoint and the backend callback URL we register as the
    # redirect_uri (must be publicly reachable so Granola can redirect back).
    GRANOLA_MCP_URL: str = os.getenv("GRANOLA_MCP_URL", "https://mcp.granola.ai/mcp")
    GRANOLA_OAUTH_REDIRECT_URI: str | None = os.getenv("GRANOLA_OAUTH_REDIRECT_URI")

    # Google Drive Picker requires TWO things distinct from the OAuth
    # client: a browser API key (`PICKER_API_KEY`) and the GCP project
    # number (`PICKER_APP_ID`). Both are visible in the Google Cloud
    # Console — the project number is the numeric id shown on the
    # project dashboard. The OAuth client_id is NOT the same thing.
    GOOGLE_PICKER_API_KEY: str | None = os.getenv("GOOGLE_PICKER_API_KEY")
    GOOGLE_PICKER_APP_ID: str | None = os.getenv("GOOGLE_PICKER_APP_ID")

    # --- LLM (Anthropic) ---
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    ANTHROPIC_FAST_MODEL: str = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5")


settings = Settings()
