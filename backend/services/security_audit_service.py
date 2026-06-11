"""Security audit trail for sensitive integration and source actions."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from ..database import get_pool


def hash_value(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def _event_row(row) -> dict:
    metadata = row["metadata"] or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]) if row["workspace_id"] else None,
        "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] else None,
        "action": row["action"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "provider": row["provider"],
        "source_type": row["source_type"],
        "metadata": metadata,
        "created_at": row["created_at"].isoformat(),
    }


async def record_event(
    *,
    action: str,
    actor_user_id: UUID | None,
    target_type: str,
    workspace_id: UUID | None = None,
    target_id: str | None = None,
    provider: str | None = None,
    source_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    await get_pool().execute(
        """
        INSERT INTO security_audit_events (
            workspace_id, actor_user_id, action, target_type, target_id,
            provider, source_type, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        """,
        workspace_id,
        actor_user_id,
        action,
        target_type,
        target_id,
        provider,
        source_type,
        json.dumps(metadata or {}),
    )


async def record_content_lifecycle_event(
    *,
    operation: str,
    actor_user_id: UUID,
    workspace_id: UUID,
    target_type: str,
    target_id: UUID,
    metadata: dict | None = None,
) -> None:
    await record_event(
        action=f"content.{target_type}_{operation}",
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata,
    )


async def record_user_event(
    *,
    action: str,
    actor_user_id: UUID,
    target_type: str,
    target_id: str | None = None,
    provider: str | None = None,
    source_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Account-scoped actions (integration connect/disconnect) have no single
    workspace. The only read surface is per-workspace, so record one event per
    workspace the actor belongs to — a NULL workspace_id row would be invisible."""
    rows = await get_pool().fetch(
        "SELECT workspace_id FROM workspace_members WHERE user_id = $1",
        actor_user_id,
    )
    for row in rows:
        await record_event(
            action=action,
            actor_user_id=actor_user_id,
            workspace_id=row["workspace_id"],
            target_type=target_type,
            target_id=target_id,
            provider=provider,
            source_type=source_type,
            metadata=metadata,
        )


async def list_workspace_events(
    *,
    workspace_id: UUID,
    action: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if action:
        rows = await get_pool().fetch(
            """
            SELECT *
            FROM security_audit_events
            WHERE workspace_id = $1 AND action = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            workspace_id,
            action,
            limit,
        )
    else:
        rows = await get_pool().fetch(
            """
            SELECT *
            FROM security_audit_events
            WHERE workspace_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            workspace_id,
            limit,
        )
    return [_event_row(row) for row in rows]
