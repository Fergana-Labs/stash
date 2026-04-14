"""Centralised settings loaded from environment variables.

All configuration that the backend touches must be declared here.
Defaults are chosen for local development with the bundled docker-compose.yml.
"""

import os


class Settings:
    # --- Server ---
    PORT: int = int(os.getenv("PORT", "3456"))

    # --- Database ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://octopus:octopus@localhost:5432/octopus"
    )
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "20"))

    # --- URLs & CORS ---
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:3457")
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3457,http://localhost:3456"
    ).split(",")

    # --- LLM ---
    # Used by the sleep agent and universal search service (Anthropic SDK reads
    # ANTHROPIC_API_KEY from the environment automatically; declared here for
    # documentation and validation purposes).
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")

    # Used by the embedding service (OpenAI SDK reads OPENAI_API_KEY
    # automatically; EMBEDDING_API_KEY is the project-specific alias).
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    EMBEDDING_API_KEY: str | None = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")

    # --- File storage (S3-compatible, e.g. Cloudflare R2) ---
    S3_ENDPOINT: str | None = os.getenv("S3_ENDPOINT")
    S3_BUCKET: str | None = os.getenv("S3_BUCKET")
    S3_ACCESS_KEY: str | None = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: str | None = os.getenv("S3_SECRET_KEY")
    S3_REGION: str = os.getenv("S3_REGION", "auto")

    # --- Auth0 (optional — required for human account SSO login) ---
    # AUTH0_DOMAIN:    e.g. dev-abc123.us.auth0.com
    # AUTH0_AUDIENCE:  API identifier registered in Auth0, e.g. https://getoctopus.com/api
    AUTH0_DOMAIN: str | None = os.getenv("AUTH0_DOMAIN")
    AUTH0_AUDIENCE: str | None = os.getenv("AUTH0_AUDIENCE")


settings = Settings()
