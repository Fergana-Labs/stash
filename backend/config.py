import os


class Settings:
    PORT: int = int(os.getenv("PORT", "3456"))
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://moltchat:moltchat@localhost:5432/moltchat"
    )
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:3457")
    MATRIX_HOMESERVER: str = os.getenv("MATRIX_HOMESERVER", "http://localhost:6167")
    MATRIX_BOT_USER: str = os.getenv("MATRIX_BOT_USER", "@moltchat-relay:localhost")
    MATRIX_BOT_PASSWORD: str = os.getenv("MATRIX_BOT_PASSWORD", "moltchat-relay-pass")
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3457,http://localhost:3456"
    ).split(",")


settings = Settings()
