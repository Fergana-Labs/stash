"""Batch move / soft-delete / restore over many tree items.

Best-effort: each item is processed independently and we return per-item
results, so one failure (no write access, wrong workspace) never blocks the
rest. Composes the existing per-item service functions — no new persistence.

move covers pages, files, folders, and tables; delete/restore cover the
soft-deletable types (pages, files) — folders and tables hard-delete, which we
deliberately keep out of a best-effort loop.
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool
from . import files_service, files_tree_service, permission_service, table_service

_MOVABLE = {"page", "file", "folder", "table"}
_TRASHABLE = {"page", "file"}


async def _authorize(object_type: str, object_id: UUID, workspace_id: UUID, user_id: UUID) -> None:
    """Raise ValueError unless the object lives in this workspace and the user
    may write it. Resolving the real workspace closes the cross-workspace hole
    where membership in the request's workspace would otherwise pass."""
    obj_ws = await permission_service.resolve_workspace_id(object_type, object_id)
    if obj_ws != workspace_id:
        raise ValueError("not found")
    if not await permission_service.check_access(
        object_type, object_id, user_id, workspace_id=workspace_id, require="write"
    ):
        raise ValueError("no write access")


async def _move_one(
    object_type: str,
    object_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    target_folder_id: UUID | None,
    move_to_root: bool,
) -> bool:
    if object_type == "page":
        page = await files_tree_service.update_page(
            object_id, workspace_id, user_id, folder_id=target_folder_id, move_to_root=move_to_root
        )
        return page is not None
    if object_type == "folder":
        folder = await files_tree_service.update_folder(
            object_id, workspace_id, parent_folder_id=target_folder_id, move_to_root=move_to_root
        )
        return folder is not None
    if object_type == "table":
        table = await table_service.update_table(
            object_id, user_id, folder_id=target_folder_id, move_to_root=move_to_root
        )
        return table is not None
    if object_type == "file":
        pool = get_pool()
        if move_to_root:
            res = await pool.execute(
                "UPDATE files SET folder_id = NULL "
                "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
                object_id,
                workspace_id,
            )
        else:
            res = await pool.execute(
                "UPDATE files SET folder_id = $3 "
                "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
                object_id,
                workspace_id,
                target_folder_id,
            )
        return res.endswith("1")
    raise ValueError(f"can't move a {object_type}")


async def _delete_one(object_type: str, object_id: UUID, workspace_id: UUID, user_id: UUID) -> bool:
    if object_type == "page":
        return await files_tree_service.delete_page(object_id, workspace_id, user_id)
    if object_type == "file":
        return await files_service.delete_file(object_id, workspace_id, user_id)
    raise ValueError(f"batch delete supports pages and files, not {object_type}")


async def _restore_one(object_type: str, object_id: UUID, workspace_id: UUID) -> bool:
    if object_type == "page":
        return await files_tree_service.restore_page(object_id, workspace_id)
    if object_type == "file":
        return await files_service.restore_file(object_id, workspace_id)
    raise ValueError(f"batch restore supports pages and files, not {object_type}")


async def _run(items: list[dict], handler) -> dict:
    """Apply `handler(object_type, object_id)` to each item, collecting per-item
    success/failure. Never raises for an individual item."""
    succeeded: list[dict] = []
    errors: list[dict] = []
    for item in items:
        ref = {"object_type": item.get("object_type"), "object_id": item.get("object_id")}
        try:
            object_id = UUID(str(item["object_id"]))
            ok = await handler(item["object_type"], object_id)
            if ok:
                succeeded.append(ref)
            else:
                errors.append({**ref, "reason": "not found"})
        except (ValueError, KeyError) as e:
            errors.append({**ref, "reason": str(e) or "invalid item"})
    return {"succeeded": succeeded, "errors": errors}


async def batch_move(
    workspace_id: UUID,
    user_id: UUID,
    items: list[dict],
    target_folder_id: UUID | None = None,
    move_to_root: bool = False,
) -> dict:
    async def handler(object_type: str, object_id: UUID) -> bool:
        if object_type not in _MOVABLE:
            raise ValueError(f"can't move a {object_type}")
        await _authorize(object_type, object_id, workspace_id, user_id)
        return await _move_one(
            object_type, object_id, workspace_id, user_id, target_folder_id, move_to_root
        )

    return await _run(items, handler)


async def batch_delete(workspace_id: UUID, user_id: UUID, items: list[dict]) -> dict:
    async def handler(object_type: str, object_id: UUID) -> bool:
        if object_type not in _TRASHABLE:
            raise ValueError(f"batch delete supports pages and files, not {object_type}")
        await _authorize(object_type, object_id, workspace_id, user_id)
        return await _delete_one(object_type, object_id, workspace_id, user_id)

    return await _run(items, handler)


async def batch_restore(workspace_id: UUID, user_id: UUID, items: list[dict]) -> dict:
    async def handler(object_type: str, object_id: UUID) -> bool:
        if object_type not in _TRASHABLE:
            raise ValueError(f"batch restore supports pages and files, not {object_type}")
        # Trashed rows can't be permission-checked the normal way (live-only
        # queries skip them); workspace membership + write is the gate.
        if not await permission_service.is_workspace_member(workspace_id, user_id):
            raise ValueError("no write access")
        return await _restore_one(object_type, object_id, workspace_id)

    return await _run(items, handler)
