"""Per-user content scope.

Each user IS their own scope. Everything a user owns is keyed by
`owner_user_id` = their user id. A workspace is a scope owned by a dedicated
login-less user; its members can read and write that scope's content like
their own — including publishing the scope's skills. Owner-only powers
(sharing, sources, per-object public links) stay with the scope user itself —
`is_owner` never matches a workspace member. A stash (see stash_service) is
also a login-less scope, but its human owner IS the owner: `is_owner` matches,
so sharing, sources, and publishing work in your own stashes.
"""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def _is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return owner_user_id is not None and owner_user_id == user_id


async def is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    from . import permission_service

    if _is_owner(owner_user_id, user_id):
        return True
    return await permission_service.is_stash_owner(owner_user_id, user_id)


async def can_read(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    from . import permission_service

    if _is_owner(owner_user_id, user_id):
        return True
    return await permission_service.is_scope_member(owner_user_id, user_id)


async def can_write(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    from . import permission_service

    if _is_owner(owner_user_id, user_id):
        return True
    return await permission_service.is_scope_member(owner_user_id, user_id)


async def seed_user_scope(user_id: UUID) -> None:
    """Provision the daily Memory curator for a new scope.

    Public Skills are opt-in and are installed from Discover, never seeded
    into accounts.
    """
    from . import agent_service

    try:
        await agent_service.get_or_create_curator(user_id)
    except Exception:
        logger.exception("curator provisioning failed for user %s", user_id)
