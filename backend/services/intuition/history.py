"""Permission-checked history discovery and bounded example excerpts for the wizard."""

from __future__ import annotations

import json
from urllib.parse import quote
from uuid import UUID

from redis.exceptions import RedisError

from stashai.local_history import bound_search, pack_page, validate_request

from ...database import get_pool
from .. import memory_service, permission_service, security_audit_service, session_service
from . import history_bridge, service


async def search(
    owner: UUID, *, query="", agent="", limit=5, offset=0, event_offset=0, source="all"
) -> dict:
    args = validate_request(
        "search",
        {
            "query": query,
            "agent": agent,
            "limit": limit,
            "offset": offset,
            "event_offset": event_offset,
        },
    )
    if source not in ("all", "recorded", "local"):
        raise ValueError("History source must be all, recorded, or local")
    result = {"results": [], "source": source}
    if source != "local":
        result.update(
            await _search_recorded(owner, **{k: v for k, v in args.items() if k != "event_offset"})
        )
    if source != "recorded":
        try:
            local = await history_bridge.request(owner, "search", args)
        except RedisError:
            local = {
                "connected": False,
                "unavailable": True,
                "message": "The local history connection is temporarily unavailable.",
            }
        seen = {r["session_id"] for r in result["results"] if r.get("session_id")}
        result["results"].extend(
            r for r in local.get("results", []) if r.get("session_id") not in seen
        )
        result["local"] = {k: v for k, v in local.items() if k != "results"}
        if local.get("connected") and not local.get("unavailable"):
            await security_audit_service.record_entries_listed(
                target_type="local_codex_history",
                actor_user_id=owner,
                owner_user_id=owner,
                metadata={"count": len(local.get("results", []))},
            )
    return bound_search(result)


async def _search_recorded(owner: UUID, query: str, agent: str, limit: int, offset: int) -> dict:
    pool = get_pool()
    access = permission_service.readable_content_condition("session", "s", 1)
    scopes = permission_service.accessible_scope_ids_sql(1)
    sessions = await pool.fetch(
        f"""SELECT s.id,s.owner_user_id,s.session_id,s.agent_name AS agent,s.cwd AS project,
          coalesce(s.title,s.session_id) AS title,s.started_at,s.last_event_at,
          left(hit.content,350) AS snippet,
          (SELECT count(*) FROM history_events e WHERE e.owner_user_id=s.owner_user_id
           AND e.session_id=s.session_id AND e.event_type=ANY($6::text[])
           AND (e.created_at,e.id)<(hit.created_at,hit.id))::int AS match_offset
        FROM sessions s JOIN LATERAL (
          SELECT e.content,e.created_at,e.id FROM history_events e
          WHERE e.owner_user_id=s.owner_user_id AND e.session_id=s.session_id
            AND e.event_type=ANY($6::text[])
            AND ($2='' OR strpos(lower(coalesce(s.title,'') || ' ' || coalesce(s.cwd,'')),lower($2))>0
              OR to_tsvector('english',e.content) @@ websearch_to_tsquery('english',$2))
          ORDER BY e.created_at,e.id LIMIT 1
        ) hit ON true
        WHERE s.deleted_at IS NULL AND s.owner_user_id IN {scopes} AND {access}
          AND (s.owner_user_id=$1 OR s.created_by=$1)
          AND ($3='' OR strpos(lower(s.agent_name),lower($3))>0)
        ORDER BY s.last_event_at DESC,s.id LIMIT $4 OFFSET $5""",
        owner,
        query,
        agent,
        limit + 1,
        offset,
        list(memory_service.RENDERABLE_EVENT_TYPES),
    )
    traces = await pool.fetch(
        """SELECT t.id,t.external_id AS session_id,t.title,t.created_at AS started_at,
          coalesce(t.metadata->>'agent',t.source_format) AS agent,t.metadata->>'cwd' AS project,
          left(hit.content,350) AS snippet,
          (SELECT count(*) FROM rm_trace_steps prior WHERE prior.trace_id=t.id AND prior.idx<hit.idx
           AND prior.role IN ('user','assistant','tool') AND coalesce(prior.metadata->>'thinking','false')<>'true')::int AS match_offset
        FROM rm_traces t JOIN LATERAL (
          SELECT s.content,s.idx FROM rm_trace_steps s WHERE s.trace_id=t.id
           AND s.role IN ('user','assistant','tool') AND coalesce(s.metadata->>'thinking','false')<>'true'
           AND ($2='' OR strpos(lower(t.title),lower($2))>0
             OR to_tsvector('english',s.content) @@ websearch_to_tsquery('english',$2))
          ORDER BY s.idx LIMIT 1
        ) hit ON true
        WHERE t.owner_user_id=$1
          AND ($3='' OR strpos(lower(coalesce(t.metadata->>'agent',t.source_format)),lower($3))>0)
          AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.owner_user_id=t.owner_user_id
            AND s.session_id=coalesce(t.metadata->>'session_id',t.external_id))
        ORDER BY t.created_at DESC,t.id LIMIT $4 OFFSET $5""",
        owner,
        query,
        agent,
        limit + 1,
        offset,
    )
    found = []
    for kind, rows in (("session", sessions), ("trace", traces)):
        for row in rows[:limit]:
            data = dict(row)
            data.pop("owner_user_id", None)
            data.pop("last_event_at", None)
            data["id"] = str(data["id"])
            data["kind"] = kind
            data["url"] = (
                f"/sessions/{quote(data['session_id'], safe='')}"
                if kind == "session"
                else f"/reward-models/traces/{data['id']}"
            )
            found.append(data)
    await security_audit_service.record_entries_listed(
        target_type="wizard_history",
        actor_user_id=owner,
        owner_user_id=owner,
        metadata={"source": "recorded", "count": len(found)},
    )
    return {
        "results": found,
        "recorded_has_more": len(sessions) > limit or len(traces) > limit,
        "recorded_next_offset": offset + limit,
    }


async def read(owner: UUID, *, kind: str, id: str, offset=0, limit=20) -> dict:
    args = validate_request("read", {"id": id, "offset": offset, "limit": limit})
    if kind == "local":
        try:
            result = await history_bridge.request(owner, "read", args)
        except RedisError as exc:
            raise ValueError("Local history is temporarily unavailable") from exc
        if not result.get("connected") or result.get("unavailable"):
            raise ValueError(result.get("message", "Local history is unavailable"))
        await security_audit_service.record_content_read(
            target_type="local_codex_session",
            target_id=id,
            actor_user_id=owner,
            owner_user_id=owner,
        )
        return result
    pool = get_pool()
    if kind == "session":
        row = await session_service.get_session_by_id(UUID(id))
        if (
            not row
            or (row["owner_user_id"] != owner and row["created_by"] != owner)
            or not await memory_service.can_read_session(
                row["owner_user_id"], row["session_id"], owner
            )
        ):
            raise service.NotFound("Session not found")
        source = {
            "kind": kind,
            "id": id,
            "session_id": row["session_id"],
            "agent": row["agent_name"],
            "url": f"/sessions/{quote(row['session_id'], safe='')}",
        }
        # Fetch only one bounded page. COUNT preserves explicit pagination for long sessions.
        total = await pool.fetchval(
            "SELECT count(*) FROM history_events WHERE owner_user_id=$1 AND session_id=$2 AND event_type=ANY($3::text[])",
            row["owner_user_id"],
            row["session_id"],
            list(memory_service.RENDERABLE_EVENT_TYPES),
        )
        rows = await pool.fetch(
            """SELECT event_type,tool_name,left(content,3001) AS content FROM history_events
             WHERE owner_user_id=$1 AND session_id=$2 AND event_type=ANY($3::text[])
             ORDER BY created_at,id LIMIT $4 OFFSET $5""",
            row["owner_user_id"],
            row["session_id"],
            list(memory_service.RENDERABLE_EVENT_TYPES),
            limit,
            offset,
        )
        events = [
            {
                "role": "user"
                if r["event_type"] in memory_service.USER_EVENT_TYPES
                else "tool"
                if r["event_type"] == "tool_result"
                else "assistant",
                "content": r["content"],
                "tool_name": r["tool_name"],
            }
            for r in rows
        ]
        audit_owner = row["owner_user_id"]
    elif kind == "trace":
        row = await pool.fetchrow(
            """SELECT id,title,external_id FROM rm_traces t WHERE t.id=$1 AND t.owner_user_id=$2
             AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.owner_user_id=t.owner_user_id
               AND s.session_id=coalesce(t.metadata->>'session_id',t.external_id) AND s.deleted_at IS NOT NULL)""",
            UUID(id),
            owner,
        )
        if not row:
            raise service.NotFound("Trace not found")
        source = {
            "kind": kind,
            "id": id,
            "title": row["title"],
            "session_id": row["external_id"],
            "url": f"/reward-models/traces/{id}",
        }
        total = await pool.fetchval(
            "SELECT count(*) FROM rm_trace_steps WHERE trace_id=$1 AND role IN ('user','assistant','tool') AND coalesce(metadata->>'thinking','false')<>'true'",
            UUID(id),
        )
        rows = await pool.fetch(
            "SELECT role,left(content,3001) AS content,tool_name,left(tool_input::text,3001) AS tool_input FROM rm_trace_steps WHERE trace_id=$1 AND role IN ('user','assistant','tool') AND coalesce(metadata->>'thinking','false')<>'true' ORDER BY idx LIMIT $2 OFFSET $3",
            UUID(id),
            limit,
            offset,
        )
        events = [
            {
                "role": r["role"],
                "content": r["content"] or r["tool_input"] or "",
                "tool_name": r["tool_name"],
            }
            for r in rows
        ]
        audit_owner = owner
    else:
        raise ValueError("Unknown history source")
    page = pack_page(source, events, 0, limit)
    for event in page["events"]:
        event["index"] += offset
    page.update(offset=offset, total=total, next_offset=offset + len(page["events"]))
    page["has_more"] = page["next_offset"] < total
    await security_audit_service.record_content_read(
        target_type="transcript" if kind == "session" else "trace",
        target_id=source["session_id"] or id,
        actor_user_id=owner,
        owner_user_id=audit_owner,
    )
    return page


async def add_examples(owner: UUID, model_id: UUID, selections: list[dict]) -> list[dict]:
    await service._model(owner, model_id)
    if not 1 <= len(selections) <= 10:
        raise ValueError("Select between one and ten history excerpts")
    existing = await service.list_examples(owner, model_id)
    seen = {json.dumps(e["item"], sort_keys=True) for e in existing}
    rows = []
    for selection in selections:
        selection = dict(selection)
        label = selection.pop("label", None)
        note = str(selection.pop("note", ""))[:1500]
        page = await read(owner, **selection)
        if not page["events"]:
            raise ValueError("This history selection has no events; choose another range")
        item = {
            "kind": "history",
            "source": page["source"],
            "events": page["events"],
            "offset": page["offset"],
            "end_offset": page["next_offset"],
            "content_truncated": page["content_truncated"],
            "partial_history": page["source"].get("partial_history", False),
        }
        key = json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "item": item,
                "label": label,
                "needs_review": True,
                "note": f"Suggested {label}: {note}"
                if label
                else "From your history; needs your label. " + note,
            }
        )
    return await service.add_examples(owner, model_id, rows, "production") if rows else []
