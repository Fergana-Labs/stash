import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "AI_COLLAB_DATABASE_URL",
        os.getenv("DATABASE_URL", ""),
    )


settings = Settings()
