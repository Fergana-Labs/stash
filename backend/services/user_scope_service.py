"""Current-user content scope helpers."""

from uuid import UUID

from . import workspace_service


async def scope_id_for_user(user_id: UUID) -> UUID | None:
    return await workspace_service.get_primary_for_user(user_id)
