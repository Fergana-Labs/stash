"""Seed the default `slides` skill into every existing user scope.

New users get this skill seeded at signup via
`backend.services.user_scope_service.seed_user_scope`. This script runs
the same seed against every existing user — useful right after the
feature lands.

Idempotent: a user that already has a `slides/SKILL.md` is skipped.

Usage:
    python scripts/backfill_slides_skill.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")

sys.path.insert(0, str(REPO_ROOT))

from backend import database  # noqa: E402
from backend.services import skill_seeds  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_slides_skill")


async def main() -> None:
    await database.init_db()
    pool = database.get_pool()
    rows = await pool.fetch("SELECT id, email FROM users ORDER BY created_at")
    created = 0
    skipped = 0
    for row in rows:
        try:
            did_create = await skill_seeds.seed_slides_skill(row["id"], row["id"])
        except Exception:
            log.exception("seed failed for user %s (%s)", row["id"], row["email"])
            continue
        if did_create:
            created += 1
            log.info("seeded slides skill: %s (%s)", row["email"], row["id"])
        else:
            skipped += 1
    log.info("done: %d seeded, %d already present", created, skipped)
    await database.close_db()


if __name__ == "__main__":
    asyncio.run(main())
