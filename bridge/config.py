import os


class BridgeSettings:
    MATRIX_HOMESERVER: str = os.getenv("MATRIX_HOMESERVER", "http://localhost:6167")
    MATRIX_BOT_USER: str = os.getenv("MATRIX_BOT_USER", "moltchat-relay")
    MATRIX_BOT_PASSWORD: str = os.getenv("MATRIX_BOT_PASSWORD", "moltchat-relay-pass")
    MOLTCHAT_API_URL: str = os.getenv("MOLTCHAT_API_URL", "http://localhost:3456")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://moltchat:moltchat@localhost:5432/moltchat"
    )


bridge_settings = BridgeSettings()
