"""Bounded, resumable input for all developer-curator source types.

The timestamp watermark never passes a partly read document. A cursor records
completed siblings and character offsets at that timestamp, so even one huge
file or a large group of simultaneous events can make progress across runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from ..database import get_pool
from . import curation_service


@dataclass
class Batch:
    documents: list[dict]
    through: datetime
    cursor: dict


async def load_batch(
    owner: UUID,
    since,
    until,
    *,
    internal: bool,
    generation: int,
    cursor: dict | None = None,
    max_chars: int = 200_000,
    max_items: int | None = None,
) -> Batch:
    baseline = since.isoformat() if since else None
    state = cursor or {}
    if state.get("since") != baseline or state.get("generation") != generation:
        state = {}
    documents = []
    done = list(state.get("done", []))
    partial = dict(state.get("partial", {}))
    remaining = max_chars
    limit = curation_service._MAX_EVENTS if max_items is None else max_items
    # Metadata only: never transfer an unbounded extracted document to the
    # worker, and never hash or measure the whole backlog. A document is hashed
    # here only when an earlier run already completed it at this timestamp.
    done_bases = [_base(key) for key in done]
    async with get_pool().acquire() as conn, conn.transaction(isolation="repeatable_read"):
        rows = await conn.fetch(
            """
            WITH inputs AS (
                SELECT 'event' AS kind, he.id, he.created_at AS stamp,
                    'event:'||he.id::text AS base,
                    'session:'||he.session_id AS document_id,
                    he.session_id AS title, s.end_user_id, he.event_type, he.tool_name
                FROM history_events he JOIN sessions s ON s.owner_user_id=he.owner_user_id
                    AND s.session_id=he.session_id
                WHERE he.owner_user_id=$1 AND s.deleted_at IS NULL
                    AND he.session_id NOT LIKE 'agent-curate-%'
                UNION ALL
                SELECT 'file', f.id, f.created_at, 'file:'||f.id::text, 'file:'||f.id::text, f.name, f.end_user_id, NULL, NULL
                FROM files f WHERE f.owner_user_id=$1 AND f.deleted_at IS NULL
                    AND f.extraction_status='done' AND f.extracted_text IS NOT NULL
                UNION ALL
                SELECT 'source', d.id, d.updated_at, 'source:'||d.id::text, 'source:'||d.id::text, d.name, s.end_user_id, NULL, NULL
                FROM drive_documents d JOIN user_sources s ON s.id=d.source_id
                WHERE d.owner_user_id=$1 AND s.owner_user_id=$1 AND d.deleted_at IS NULL
                    AND d.extraction_status='done' AND d.content IS NOT NULL
            )
            SELECT kind,id,stamp,base,document_id,title,end_user_id,event_type,tool_name
            FROM inputs WHERE ($2::timestamptz IS NULL OR stamp>$2) AND stamp<=$3
                AND ((end_user_id IS NULL)=$4)
                AND (base<>ALL($7::text[]) OR coalesce(base||':'||CASE kind
                    WHEN 'file' THEN (SELECT md5(extracted_text) FROM files WHERE id=inputs.id)
                    WHEN 'source' THEN (SELECT md5(content) FROM drive_documents WHERE id=inputs.id)
                    END,base)<>ALL($5::text[]))
            ORDER BY stamp,kind,id LIMIT $6
            """,
            owner,
            since,
            until,
            internal,
            done,
            limit + 1,
            done_bases,
        )
        completed = []
        pending_stamp = None
        for index, row in enumerate(rows):
            if index >= limit or remaining < 1024:
                pending_stamp = row["stamp"]
                break
            table, column = {
                "event": ("history_events", "content"),
                "file": ("files", "extracted_text"),
                "source": ("drive_documents", "content"),
            }[row["kind"]]
            # Revised files and sources get a new key, so a stale offset or a
            # completed marker never applies to their new text.
            row = {
                **dict(row),
                "key": row["base"]
                if row["kind"] == "event"
                else row["base"]
                + ":"
                + await conn.fetchval(f"SELECT md5({column}) FROM {table} WHERE id=$1", row["id"]),
            }
            offset = int(partial.get(row["key"], 0))
            text, row["characters"] = await conn.fetchrow(
                f"SELECT substring(coalesce({column},'') FROM $2::integer FOR $3::integer), "
                f"length(coalesce({column},'')) FROM {table} WHERE id=$1",
                row["id"],
                offset + 1,
                remaining,
            )

            # History envelopes count too. Binary-search the largest complete
            # JSON fragment fitting the remaining budget; never cut JSON bytes.
            def render(chunk):
                if row["kind"] != "event":
                    return chunk
                return (
                    json.dumps(
                        {
                            "event_type": row["event_type"],
                            "tool_name": row["tool_name"],
                            "content": chunk,
                            "created_at": row["stamp"].isoformat(),
                            "offset": offset,
                            "total_characters": row["characters"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            if len(render(text)) <= remaining:
                lo = len(text)
            else:
                lo, hi = 0, len(text) - 1
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if len(render(text[:mid])) <= remaining:
                        lo = mid
                    else:
                        hi = mid - 1
            content = render(text[:lo])
            documents.append(
                {**row, "content": content, "offset": offset, "next_offset": offset + lo}
            )
            remaining -= len(content)
            if offset + lo < row["characters"]:
                partial[row["key"]] = offset + lo
                pending_stamp = row["stamp"]
                completed.append(row)
                break
            partial.pop(row["key"], None)
            completed.append(row)
        if pending_stamp is None:
            return Batch(documents, until, {})
        through = pending_stamp - timedelta(microseconds=1)
        # Old completed siblings are relevant only while the watermark stays
        # at their timestamp; newer timestamps start with an empty sibling set.
        if since != through:
            done = []
            partial = {
                r["key"]: partial[r["key"]]
                for r in completed
                if r["stamp"] == pending_stamp and r["key"] in partial
            }
        done.extend(
            r["key"] for r in completed if r["stamp"] == pending_stamp and r["key"] not in partial
        )
        return Batch(
            documents,
            through,
            {
                "since": through.isoformat(),
                "generation": generation,
                "done": done,
                "partial": partial,
            },
        )


def _base(key: str) -> str:
    """'event:<id>' keys have no digest; file and source keys end in ':<md5>'."""
    return key if key.startswith("event:") else key.rsplit(":", 1)[0]


async def has_pending(agent: dict, workspace: dict, *, until: datetime | None = None) -> bool:
    """Only eligible source input, never the curator's own wiki writes."""
    from datetime import UTC

    batch = await load_batch(
        UUID(str(agent["user_id"])),
        agent["curated_through"],
        until or datetime.now(UTC),
        internal=agent["curator_wiki"] == "internal",
        generation=workspace["curation_generation"],
        cursor=agent.get("curation_cursor"),
        max_chars=1024,
        max_items=1,
    )
    return bool(batch.documents)
