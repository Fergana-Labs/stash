"""Linear ticket labels extracted from session transcript text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from ..database import get_pool
from . import linear_api_service

LINEAR_TICKET_ID = r"[A-Z][A-Z0-9]+-\d+"

_TICKET_PATTERNS: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (
        re.compile(
            rf"You are working on a Linear ticket [`']?(?P<ticket>{LINEAR_TICKET_ID})[`']?",
            re.IGNORECASE,
        ),
        "linear_preamble",
        1.0,
    ),
    (
        re.compile(rf"\bIdentifier:\s*(?P<ticket>{LINEAR_TICKET_ID})\b", re.IGNORECASE),
        "linear_preamble",
        1.0,
    ),
    (
        re.compile(
            rf"https?://linear\.app/[^\s)]+/issue/(?P<ticket>{LINEAR_TICKET_ID})(?P<tail>[^\s)]*)",
            re.IGNORECASE,
        ),
        "linear_url",
        0.95,
    ),
)


@dataclass
class LinearTicketLabel:
    ticket_identifier: str
    ticket_title: str | None
    ticket_url: str | None
    source: str
    confidence: float
    linear_issue_id: str | None = None
    ticket_status: str | None = None
    ticket_assignee_name: str | None = None
    ticket_team_key: str | None = None
    ticket_team_name: str | None = None
    ticket_project_name: str | None = None
    linear_updated_at: str | None = None
    enriched_at: str | None = None


def ticket_response(label: dict) -> dict:
    return {
        "ticket_identifier": label["ticket_identifier"],
        "ticket_title": label.get("ticket_title"),
        "ticket_url": label.get("ticket_url"),
        "source": label["source"],
        "confidence": float(label["confidence"]),
        "linear_issue_id": label.get("linear_issue_id"),
        "ticket_status": label.get("ticket_status"),
        "ticket_assignee_name": label.get("ticket_assignee_name"),
        "ticket_team_key": label.get("ticket_team_key"),
        "ticket_team_name": label.get("ticket_team_name"),
        "ticket_project_name": label.get("ticket_project_name"),
        "linear_updated_at": _timestamp_response(label.get("linear_updated_at")),
        "enriched_at": _timestamp_response(label.get("enriched_at")),
    }


def tickets_response(labels: list[dict] | tuple[dict, ...] | None) -> list[dict]:
    return [ticket_response(label) for label in labels or []]


def extract_labels(contents: list[str]) -> list[LinearTicketLabel]:
    labels: dict[str, LinearTicketLabel] = {}
    for content in contents:
        for pattern, source, confidence in _TICKET_PATTERNS:
            for match in pattern.finditer(content):
                ticket_identifier = match.group("ticket").upper()
                next_label = LinearTicketLabel(
                    ticket_identifier=ticket_identifier,
                    ticket_title=_title_for(content, ticket_identifier),
                    ticket_url=_url_for(content, ticket_identifier),
                    source=source,
                    confidence=confidence,
                )
                labels[ticket_identifier] = _merge_label(
                    labels.get(ticket_identifier),
                    next_label,
                )

    return [labels[key] for key in sorted(labels)]


def has_ticket_hint(contents: list[str]) -> bool:
    return bool(extract_labels(contents))


async def sync_session_labels(
    workspace_id: UUID,
    session_row_id: UUID,
    session_id: str,
) -> None:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT content FROM history_events "
        "WHERE workspace_id = $1 AND session_id = $2 "
        "ORDER BY created_at, id",
        workspace_id,
        session_id,
    )
    labels = extract_labels([row["content"] for row in rows])

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM session_linear_tickets WHERE session_row_id = $1",
                session_row_id,
            )
            if not labels:
                return
            await conn.executemany(
                "INSERT INTO session_linear_tickets "
                "(workspace_id, session_row_id, ticket_identifier, ticket_title, "
                "ticket_url, source, confidence) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                [
                    (
                        workspace_id,
                        session_row_id,
                        label.ticket_identifier,
                        label.ticket_title,
                        label.ticket_url,
                        label.source,
                        label.confidence,
                    )
                    for label in labels
                ],
            )
    enqueue_session_enrichment(workspace_id, session_row_id)


def enqueue_session_enrichment(workspace_id: UUID, session_row_id: UUID) -> None:
    if not linear_api_service.is_configured():
        return
    from ..tasks.linear_tickets import enrich_session_linear_tickets

    enrich_session_linear_tickets.delay(str(workspace_id), str(session_row_id))


async def enrich_session_labels(session_row_id: UUID) -> int:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ticket_identifier FROM session_linear_tickets "
        "WHERE session_row_id = $1 ORDER BY ticket_identifier",
        session_row_id,
    )

    updated = 0
    for row in rows:
        issue = await linear_api_service.fetch_issue(row["ticket_identifier"])
        if not issue:
            await pool.execute(
                "UPDATE session_linear_tickets SET enriched_at = now(), updated_at = now() "
                "WHERE session_row_id = $1 AND ticket_identifier = $2",
                session_row_id,
                row["ticket_identifier"],
            )
            continue

        await pool.execute(
            """
            UPDATE session_linear_tickets SET
              linear_issue_id = $2,
              ticket_title = $3,
              ticket_url = $4,
              ticket_status = $5,
              ticket_assignee_name = $6,
              ticket_team_key = $7,
              ticket_team_name = $8,
              ticket_project_name = $9,
              linear_updated_at = $10,
              enriched_at = now(),
              updated_at = now()
            WHERE session_row_id = $1 AND ticket_identifier = $11
            """,
            session_row_id,
            issue.issue_id,
            issue.title,
            issue.url,
            issue.status,
            issue.assignee_name,
            issue.team_key,
            issue.team_name,
            issue.project_name,
            issue.updated_at,
            row["ticket_identifier"],
        )
        updated += 1
    return updated


async def enrich_stale_sessions(limit: int) -> int:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT session_row_id
        FROM session_linear_tickets
        WHERE enriched_at IS NULL
           OR enriched_at < now() - interval '6 hours'
        GROUP BY session_row_id
        ORDER BY MIN(COALESCE(enriched_at, created_at)) ASC
        LIMIT $1
        """,
        limit,
    )

    updated = 0
    for row in rows:
        updated += await enrich_session_labels(row["session_row_id"])
    return updated


async def list_session_labels(session_row_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ticket_identifier, ticket_title, ticket_url, source, confidence, "
        "linear_issue_id, ticket_status, ticket_assignee_name, ticket_team_key, "
        "ticket_team_name, ticket_project_name, linear_updated_at, enriched_at "
        "FROM session_linear_tickets "
        "WHERE session_row_id = $1 "
        "ORDER BY ticket_identifier",
        session_row_id,
    )
    return [ticket_response(dict(row)) for row in rows]


def sql_json_agg(table_alias: str = "s") -> str:
    return (
        "COALESCE((SELECT jsonb_agg(jsonb_build_object("
        "'ticket_identifier', slt.ticket_identifier, "
        "'ticket_title', slt.ticket_title, "
        "'ticket_url', slt.ticket_url, "
        "'source', slt.source, "
        "'confidence', slt.confidence, "
        "'linear_issue_id', slt.linear_issue_id, "
        "'ticket_status', slt.ticket_status, "
        "'ticket_assignee_name', slt.ticket_assignee_name, "
        "'ticket_team_key', slt.ticket_team_key, "
        "'ticket_team_name', slt.ticket_team_name, "
        "'ticket_project_name', slt.ticket_project_name, "
        "'linear_updated_at', slt.linear_updated_at, "
        "'enriched_at', slt.enriched_at"
        ") ORDER BY slt.ticket_identifier) "
        "FROM session_linear_tickets slt "
        f"WHERE slt.session_row_id = {table_alias}.id), '[]'::jsonb)"
    )


def _merge_label(
    current: LinearTicketLabel | None,
    next_label: LinearTicketLabel,
) -> LinearTicketLabel:
    if current is None:
        return next_label

    source = current.source
    if _source_rank(next_label.source) > _source_rank(current.source):
        source = next_label.source

    return LinearTicketLabel(
        ticket_identifier=current.ticket_identifier,
        ticket_title=current.ticket_title or next_label.ticket_title,
        ticket_url=current.ticket_url or next_label.ticket_url,
        source=source,
        confidence=max(current.confidence, next_label.confidence),
    )


def _source_rank(source: str) -> int:
    if source == "linear_preamble":
        return 3
    if source == "linear_url":
        return 2
    return 1


def _title_for(content: str, ticket_identifier: str) -> str | None:
    pattern = re.compile(
        rf"\bIdentifier:\s*{re.escape(ticket_identifier)}\b.*?\nTitle:\s*(?P<title>[^\n\r]+)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        return None
    title = match.group("title").strip()
    return title or None


def _url_for(content: str, ticket_identifier: str) -> str | None:
    pattern = re.compile(
        rf"https?://linear\.app/[^\s)]+/issue/{re.escape(ticket_identifier)}[^\s)]*",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return None
    return match.group(0).rstrip(".,;]")


def _timestamp_response(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
