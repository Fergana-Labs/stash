import os


class Settings:
    PORT: int = int(os.getenv("PORT", "3456"))
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://boozle:boozle@localhost:5432/boozle"
    )
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:3457")
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3457,http://localhost:3456"
    ).split(",")


settings = Settings()
