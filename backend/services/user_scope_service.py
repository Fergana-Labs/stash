"""Per-user content scope.

Each user IS their own scope. Everything a user owns is keyed by
`owner_user_id` = their user id; there is no separate scope entity.
A user can read their own content, plus anything shared with them (the `shares`
table) and anything published (skills). Writing is owner-only.
"""

import logging
from uuid import UUID

from . import skill_seeds

logger = logging.getLogger(__name__)


async def scope_id_for_user(user_id: UUID) -> UUID:
    """The user's scope id is just the user id."""
    return user_id


def _is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return owner_user_id is not None and owner_user_id == user_id


# Access helpers kept async with stable names so call sites stay `await ...(owner, user)`.
# Every one reduces to "is this your own scope?" — non-owners get access via shares.
async def is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def is_member(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def can_read(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def can_write(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def get_member_role(owner_user_id: UUID | None, user_id: UUID | None) -> str | None:
    return "owner" if _is_owner(owner_user_id, user_id) else None


async def seed_user_scope(user_id: UUID) -> None:
    """Provision a new user's scope: seed the default slides skill so the agent
    can discover it. Best-effort; failures must not block signup."""
    try:
        await skill_seeds.seed_slides_skill(user_id, user_id)
    except Exception:
        logger.exception("seed_slides_skill failed for user %s", user_id)
