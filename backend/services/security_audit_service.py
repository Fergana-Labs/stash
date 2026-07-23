"""Security audit trail for sensitive integration and source actions."""

from __future__ import annotations

import hashlib
import hmac
import json
from contextvars import ContextVar
from uuid import UUID

from ..config import settings
from ..database import get_pool

# The caller surface of the current request — 'web', 'cli', or 'ask' — set by
# auth on every authenticated request and stamped onto each audit row. A
# contextvar (not a parameter) so the many record_event call sites don't all
# have to thread a Request through. None (e.g. the anonymous paste route)
# stores NULL, which the per-surface dashboard excludes.
request_via: ContextVar[str | None] = ContextVar("request_via", default=None)


def hash_value(value: str | None) -> str | None:
    """Keyed HMAC, not a plain hash: redacted values are often low-entropy
    (emails, IPv4s), so an unkeyed digest could be reversed offline by hashing
    candidate values."""
    if value is None:
        return None
    return hmac.new(settings.AUDIT_HASH_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _event_row(row) -> dict:
    metadata = row["metadata"] or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {
        "id": str(row["id"]),
        "owner_user_id": str(row["owner_user_id"]) if row["owner_user_id"] else None,
        "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] else None,
        "action": row["action"],
        "via": row["via"],
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
    owner_user_id: UUID | None = None,
    target_id: str | None = None,
    provider: str | None = None,
    source_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    await get_pool().execute(
        """
        INSERT INTO security_audit_events (
            owner_user_id, actor_user_id, action, target_type, target_id,
            provider, source_type, metadata, via
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
        """,
        owner_user_id,
        actor_user_id,
        action,
        target_type,
        target_id,
        provider,
        source_type,
        json.dumps(metadata or {}),
        request_via.get(),
    )


async def record_content_lifecycle_event(
    *,
    operation: str,
    actor_user_id: UUID,
    owner_user_id: UUID,
    target_type: str,
    target_id: UUID,
    metadata: dict | None = None,
) -> None:
    await record_event(
        action=f"content.{target_type}_{operation}",
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata,
    )


async def record_content_read(
    *,
    target_type: str,
    target_id: str | None,
    actor_user_id: UUID | None,
    owner_user_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    """Read trail for native content (pages, files, transcripts, tables, ...).

    Connected-source reads are audited separately in source_service
    (source.document_read); together the two cover every document read.
    actor_user_id is None for anonymous public-link reads."""
    await record_event(
        action=f"content.{target_type}_read",
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata,
    )


async def record_entries_listed(
    *,
    target_type: str,
    actor_user_id: UUID,
    owner_user_id: UUID,
    metadata: dict | None = None,
) -> None:
    """Listing trail for native content (tree, overview, tables, ...) —
    parallel to source.entries_listed for connected sources."""
    await record_event(
        action="content.entries_listed",
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        target_type=target_type,
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
    target scope. The actor's scope is their own user id, so record one event
    against it — a NULL owner_user_id row would be invisible to the read surface."""
    await record_event(
        action=action,
        actor_user_id=actor_user_id,
        owner_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        provider=provider,
        source_type=source_type,
        metadata=metadata,
    )


async def list_events(
    *,
    owner_user_id: UUID,
    action: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if action:
        rows = await get_pool().fetch(
            """
            SELECT *
            FROM security_audit_events
            WHERE owner_user_id = $1 AND action = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            owner_user_id,
            action,
            limit,
        )
    else:
        rows = await get_pool().fetch(
            """
            SELECT *
            FROM security_audit_events
            WHERE owner_user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            owner_user_id,
            limit,
        )
    return [_event_row(row) for row in rows]
