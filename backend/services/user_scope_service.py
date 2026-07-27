"""Per-user content scope.

Each user IS their own scope. Everything a user owns is keyed by
`owner_user_id` = their user id. A workspace is a scope owned by a dedicated
login-less user; its members can read and write that scope's content like
their own — including publishing the scope's skills. Owner-only powers
(sharing, sources, per-object public links) stay with the scope user itself —
`is_owner` never matches a member.
"""

import logging
from uuid import UUID

from . import skill_seeds

logger = logging.getLogger(__name__)


def _is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return owner_user_id is not None and owner_user_id == user_id


async def is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def can_read(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    from . import permission_service

    if _is_owner(owner_user_id, user_id):
        return True
    return await permission_service.is_workspace_member(owner_user_id, user_id)


async def can_write(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    from . import permission_service

    if _is_owner(owner_user_id, user_id):
        return True
    return await permission_service.is_workspace_member(owner_user_id, user_id)


async def seed_user_scope(user_id: UUID) -> None:
    """Provision a new user's scope: seed the default skills (slides + the
    generate-output skills) so agents can discover them, and the daily Memory
    curator so sleep-time curation works for every account — including
    API-key-only production integrations that never touch chat. Best-effort;
    failures must not block signup."""
    from . import agent_service

    try:
        await skill_seeds.seed_default_skills(user_id, user_id)
    except Exception:
        logger.exception("seed_default_skills failed for user %s", user_id)
    try:
        await agent_service.get_or_create_curator(user_id)
    except Exception:
        logger.exception("curator provisioning failed for user %s", user_id)
