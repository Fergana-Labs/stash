"""Per-user content scope.

Each user IS their own scope. Everything a user owns is keyed by
`owner_user_id` = their user id. A workspace is a scope owned by a dedicated
login-less user; its members can read and write that scope's content like
their own — including publishing the scope's skills. Owner-only powers
(sharing, per-object public links) stay with the scope user itself —
`is_owner` never matches a member. Configuring a workspace's sources is the
one exception, and it goes through `can_manage_scope`.
"""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def _is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return owner_user_id is not None and owner_user_id == user_id


async def is_owner(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    return _is_owner(owner_user_id, user_id)


async def can_manage_scope(owner_user_id: UUID | None, user_id: UUID | None) -> bool:
    """May configure this scope — connect and disconnect its sources.

    The owner of a personal scope, or the human who created the workspace. A
    workspace's scope user is login-less, so without the creator branch nobody
    could manage a workspace's sources from the app at all: a one-man developer
    workspace could not connect a customer's Drive folder without minting a
    machine key first.

    Deliberately narrower than membership. A teammate reads the workspace's
    Drive; they don't get to disconnect it or widen a Slack allowlist. Admin-
    provisioned workspaces have no `created_by` and so stay machine-key only.
    """
    from ..database import get_pool

    if _is_owner(owner_user_id, user_id):
        return True
    if owner_user_id is None or user_id is None:
        return False
    creator = await get_pool().fetchval(
        "SELECT created_by FROM workspaces WHERE scope_user_id = $1", owner_user_id
    )
    return creator is not None and creator == user_id


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
    """Provision the daily Memory curator for a new scope.

    Public Skills are opt-in and are installed from Discover, never seeded
    into accounts.
    """
    from . import agent_service

    try:
        await agent_service.get_or_create_curator(user_id)
    except Exception:
        logger.exception("curator provisioning failed for user %s", user_id)
