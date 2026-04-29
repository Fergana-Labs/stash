"""Centralised settings loaded from environment variables.

All configuration that the backend touches must be declared here.
Defaults are chosen for local development with the bundled docker-compose.yml.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


class Settings:
    # --- Server ---
    PORT: int = int(os.getenv("PORT", "3456"))

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://stash:stash@localhost:5432/stash")
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "20"))

    # --- URLs & CORS ---
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:3457")
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3457,http://localhost:3456").split(",")
        if o.strip()
    ]

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
    S3_ENDPOINT: str | None = os.getenv("S3_ENDPOINT")
    S3_BUCKET: str | None = os.getenv("S3_BUCKET")
    S3_ACCESS_KEY: str | None = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: str | None = os.getenv("S3_SECRET_KEY")
    S3_REGION: str = os.getenv("S3_REGION", "auto")

    # --- Auth0 (managed deployment only) ---
    # When AUTH0_ENABLED=true, password login/register is disabled and the
    # managed auth0 router is mounted at /api/v1/auth0/. Requires the
    # managed/ directory to be present in the deployment.
    AUTH0_ENABLED: bool = os.getenv("AUTH0_ENABLED", "false").lower() == "true"
    AUTH0_DOMAIN: str | None = os.getenv("AUTH0_DOMAIN")
    AUTH0_AUDIENCE: str | None = os.getenv("AUTH0_AUDIENCE")

    # --- Email (Postmark) ---
    POSTMARK_SERVER_TOKEN: str | None = os.getenv("POSTMARK_SERVER_TOKEN")


settings = Settings()
