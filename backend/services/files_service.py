"""Files (uploaded blobs) soft-delete service.

Mirrors files_tree_service for pages. Hard deletes (purge) also drop the
S3 blob; soft deletes leave it intact so restore is fully reversible.
"""

from uuid import UUID

from ..database import get_pool
from . import security_audit_service


async def delete_file(file_id: UUID, owner_user_id: UUID, deleted_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE files SET deleted_at = NOW(), deleted_by = $3 "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
        deleted_by,
    )
    if result != "UPDATE 1":
        return False
    # Audited here so every front door (REST, batch, agent tools) leaves a trail.
    await security_audit_service.record_content_lifecycle_event(
        operation="deleted",
        actor_user_id=deleted_by,
        owner_user_id=owner_user_id,
        target_type="file",
        target_id=file_id,
    )
    return True


async def restore_file(file_id: UUID, owner_user_id: UUID, restored_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE files SET deleted_at = NULL, deleted_by = NULL "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        file_id,
        owner_user_id,
    )
    if result != "UPDATE 1":
        return False
    await security_audit_service.record_content_lifecycle_event(
        operation="restored",
        actor_user_id=restored_by,
        owner_user_id=owner_user_id,
        target_type="file",
        target_id=file_id,
    )
    return True


async def get_trashed_file(file_id: UUID, owner_user_id: UUID) -> dict | None:
    """Return the trashed row (or None). Used by purge to grab storage_key."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, storage_key FROM files "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        file_id,
        owner_user_id,
    )
    return dict(row) if row else None


async def storage_key_referenced_elsewhere(file_id: UUID, storage_key: str) -> bool:
    """Forks copy storage_key by reference (shared_skill_service._fork_file /
    _fork_session), so other files rows or session artifacts can point at the
    same S3 object. Purge must keep the blob alive for them."""
    pool = get_pool()
    return await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM files WHERE storage_key = $1 AND id <> $2) "
        "OR EXISTS (SELECT 1 FROM session_artifacts WHERE storage_key = $1)",
        storage_key,
        file_id,
    )


async def purge_file(file_id: UUID, owner_user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM files WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        file_id,
        owner_user_id,
    )
    return result == "DELETE 1"


async def list_trashed_files(owner_user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, owner_user_id, folder_id, name, content_type, size_bytes, "
        "deleted_at, deleted_by "
        "FROM files WHERE owner_user_id = $1 AND deleted_at IS NOT NULL "
        "ORDER BY deleted_at DESC",
        owner_user_id,
    )
    return [dict(r) for r in rows]
