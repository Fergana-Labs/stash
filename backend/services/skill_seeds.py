"""Default skills seeded into every scope.

An agent can only use a skill that lives in the user's own scope —
`list_skills` reads folders with a SKILL.md in this Stash account, not the
published-skills table. So seeding is what makes a skill *usable*; publishing
(the `skills` table, Discover) is what makes it *findable*. They are
different jobs, and a skill generally wants both.

The content lives in `backend/skills/<name>/SKILL.md` rather than in Python
string constants, so a skill can be reviewed as a diff, read on GitHub, and
edited without touching code. Adding a skill means adding a directory.

Seeding is idempotent per skill: if a scope already has a folder of that name
containing a SKILL.md we leave it alone, because the user may have edited it.
That also means an improved skill does not reach existing users — see
`docs/skills.md` for why that is deliberate and what the fix would look like.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from pathlib import Path
from uuid import UUID

from ..database import get_pool
from . import files_tree_service

logger = logging.getLogger(__name__)

SKILL_MD_NAME = "SKILL.md"
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

# Env knob so the test suite can create blank scopes. Production leaves this
# unset; tests that need the seeded skills flip it off and call
# `seed_default_skills` directly.
DISABLE_ENV_VAR = "STASH_DISABLE_DEFAULT_SKILL_SEEDS"


@cache
def default_skills() -> list[tuple[str, str]]:
    """(folder name, SKILL.md body) for every skill in backend/skills.

    Sorted so seed order is stable across machines — directory iteration
    order is not. Cached because the files ship with the image and cannot
    change under a running process.
    """
    skills = []
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skills.append((path.parent.name, path.read_text()))
    if not skills:
        logger.warning("no skills found under %s", SKILLS_DIR)
    return skills


def skill_markdown(name: str) -> str:
    """One skill's SKILL.md body. Raises if it's missing rather than returning
    empty — a caller embedding a skill (the landing-page demo) must not ship
    a blank one."""
    body = dict(default_skills()).get(name)
    if body is None:
        raise KeyError(f"no skill named {name!r} under {SKILLS_DIR}")
    return body


async def seed_default_skills(owner_user_id: UUID, creator_id: UUID) -> int:
    """Seed every default skill the scope doesn't already have. Returns how
    many SKILL.md pages were created. No-op when the env knob
    `STASH_DISABLE_DEFAULT_SKILL_SEEDS=1` is set (test mode)."""
    if os.environ.get(DISABLE_ENV_VAR) == "1":
        return 0
    created = 0
    for folder_name, markdown in default_skills():
        if await _seed_skill(owner_user_id, creator_id, folder_name, markdown):
            created += 1
    return created


async def _seed_skill(
    owner_user_id: UUID, creator_id: UUID, folder_name: str, markdown: str
) -> bool:
    """Create `<folder_name>/SKILL.md` in the scope if it doesn't exist.

    Returns True if the SKILL.md was created in this call, False if a
    SKILL.md was already present in any folder with that name (we treat
    that as "already seeded" and leave it alone — users may have edited it).
    """
    pool = get_pool()

    existing = await pool.fetchval(
        "SELECT p.id FROM pages p "
        "JOIN folders f ON f.id = p.folder_id "
        "WHERE f.owner_user_id = $1 AND lower(f.name) = $2 "
        "  AND p.name = $3 AND p.deleted_at IS NULL "
        "LIMIT 1",
        owner_user_id,
        folder_name,
        SKILL_MD_NAME,
    )
    if existing:
        return False

    folder_row = await pool.fetchrow(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND lower(name) = $2 "
        "  AND parent_folder_id IS NULL LIMIT 1",
        owner_user_id,
        folder_name,
    )
    if folder_row:
        folder_id = folder_row["id"]
    else:
        folder = await files_tree_service.create_folder(
            owner_user_id=owner_user_id,
            name=folder_name,
            created_by=creator_id,
        )
        folder_id = folder["id"]

    await files_tree_service.create_page(
        owner_user_id=owner_user_id,
        name=SKILL_MD_NAME,
        created_by=creator_id,
        folder_id=folder_id,
        content=markdown,
        content_type="markdown",
    )
    logger.info("seeded %s skill for scope %s", folder_name, owner_user_id)
    return True
