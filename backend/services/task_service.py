from __future__ import annotations

from uuid import UUID

from ..database import get_pool


async def register_task(
    *,
    task_id: str,
    user_id: UUID,
    workspace_id: UUID | None,
    task_type: str,
    object_type: str | None = None,
    object_id: UUID | None = None,
) -> None:
    await get_pool().execute(
        """
        INSERT INTO task_records
            (task_id, user_id, workspace_id, task_type, object_type, object_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        task_id,
        user_id,
        workspace_id,
        task_type,
        object_type,
        object_id,
    )


async def user_can_read_task(task_id: str, user_id: UUID) -> bool:
    row = await get_pool().fetchrow(
        "SELECT 1 FROM task_records WHERE task_id = $1 AND user_id = $2",
        task_id,
        user_id,
    )
    return row is not None
