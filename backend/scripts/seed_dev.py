"""Dev-only seed: a demo user plus one fake connected source per provider.

Connecting a source normally requires a real OAuth handshake, so nothing
source-backed (the integrations page, source sharing, the VFS `/sources`
tree) is demoable locally without one. This writes `user_sources` rows
directly through `create_source`, bypassing OAuth, so the whole surface
renders with one command. Tokens live in a separate table the listing path
never reads, so a bare source row is enough to show up — a real sync or live
read would still 401 until a provider is actually connected.

Refuses to run under Auth0: this is the password / DB-bypass path.

Run against a migrated dev DB (start the backend first, which migrates):
    python -m backend.scripts.seed_dev
    docker compose exec backend python -m backend.scripts.seed_dev
"""

import asyncio
import sys

from ..auth import create_api_key
from ..config import settings
from ..database import close_db, init_pool
from ..services import source_service, user_service

DEMO_NAME = "demo"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demopass123"

# One fake source per provider (google has two). Each external_ref / settings
# satisfies that type's validation: jira wants "{cloudId}:{projectKey}", linear
# must be "me", and slack needs at least one channel id.
SEED_SOURCES = [
    {
        "source_type": "github_repo",
        "external_ref": "demo-org/demo-repo",
        "display_name": "demo-org/demo-repo",
    },
    {"source_type": "google_drive", "external_ref": "root", "display_name": "Google Drive"},
    {
        "source_type": "google_drive_folder",
        "external_ref": "demo-folder",
        "display_name": "Q3 Planning Docs",
    },
    {
        "source_type": "gmail",
        "external_ref": "demo@example.com",
        "display_name": "Gmail (demo@example.com)",
    },
    {"source_type": "notion", "external_ref": "demo-notion", "display_name": "Product Wiki"},
    {
        "source_type": "slack",
        "external_ref": "T0DEMO",
        "display_name": "Acme Slack",
        "settings": {"allowed_channel_ids": ["C0DEMO001"]},
    },
    {"source_type": "granola", "external_ref": "demo-granola", "display_name": "Granola"},
    {
        "source_type": "jira_project",
        "external_ref": "democloud:DEMO",
        "display_name": "DEMO project",
    },
    {"source_type": "asana_project", "external_ref": "demo-asana", "display_name": "Roadmap"},
    {"source_type": "linear", "external_ref": "me", "display_name": "Linear"},
    {"source_type": "gong_calls", "external_ref": "demo-gong", "display_name": "Gong"},
    {"source_type": "x_saves", "external_ref": "saves", "display_name": "X saves"},
    {"source_type": "instagram_saves", "external_ref": "saves", "display_name": "Instagram saves"},
]


async def _demo_user() -> tuple[dict, str]:
    """The demo user and a fresh API key. Idempotent: on re-run it reuses the
    existing account and just mints a new key."""
    existing = await user_service.get_user_by_email(DEMO_EMAIL)
    if existing:
        return existing, await create_api_key(existing["id"], name="dev seed", key_type="manual")
    return await user_service.register_user(
        name=DEMO_NAME,
        display_name="Demo User",
        email=DEMO_EMAIL,
        password=DEMO_PASSWORD,
    )


async def _run() -> None:
    await init_pool()
    try:
        user, api_key = await _demo_user()
        print("Seeded sources:")
        for spec in SEED_SOURCES:
            source = await source_service.create_source(owner_user_id=user["id"], **spec)
            print(f"  {source['source_type']:20} {source['display_name']}")

        print()
        print(f"Demo user: {user['name']} <{DEMO_EMAIL}>  (password: {DEMO_PASSWORD})")
        print(f"API key:   {api_key}")
        print()
        print("Log in locally: in the browser console at http://localhost:3457 run")
        print(f"  localStorage.setItem('stash_token', '{api_key}')")
        print("then reload. Sources appear under /integrations/<provider>.")
    finally:
        await close_db()


def main() -> None:
    if settings.AUTH0_ENABLED:
        print(
            "Refusing to seed: AUTH0_ENABLED is true — this is the dev/password path.",
            file=sys.stderr,
        )
        sys.exit(1)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
