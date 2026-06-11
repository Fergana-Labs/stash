"""Gong → gong_documents indexer (copied content; FTS-searchable).

One Gong connection = one source (external_ref "calls"). We pull calls from a
rolling window (last LOOKBACK_DAYS) plus their transcripts in two paged passes,
then write each call as a text document (title + date + speaker-labelled
transcript). Idempotent re-sync via source_service; calls that age out of the
window are soft-deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token
from .provider import API_BASE, basic_auth_header

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 90
MAX_CALLS = 5000


def _call_workspace_id(meta: dict) -> str:
    return str(meta.get("workspaceId") or "")


def _render_call(meta: dict, monologues: list[dict]) -> str:
    title = meta.get("title") or "Untitled call"
    started = meta.get("started") or ""
    lines = [f"# {title}", f"Date: {started}", ""]
    speaker_num: dict[str, int] = {}
    for mono in monologues:
        sid = mono.get("speakerId") or "?"
        if sid not in speaker_num:
            speaker_num[sid] = len(speaker_num) + 1
        text = " ".join(s.get("text", "") for s in mono.get("sentences", []))
        if text.strip():
            lines.append(f"[Speaker {speaker_num[sid]}]: {text}")
    return "\n".join(lines)


async def _fetch_call_meta(client: httpx.AsyncClient, from_dt: str, to_dt: str) -> dict[str, dict]:
    meta_by_id: dict[str, dict] = {}
    cursor: str | None = None
    while len(meta_by_id) < MAX_CALLS:
        params = {"fromDateTime": from_dt, "toDateTime": to_dt}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(f"{API_BASE}/v2/calls", params=params)
        if resp.status_code == 404:
            break  # no calls in window
        resp.raise_for_status()
        payload = resp.json()
        for call in payload.get("calls", []):
            meta_by_id[call["id"]] = call
        cursor = (payload.get("records") or {}).get("cursor")
        if not cursor:
            break
    return meta_by_id


async def _fetch_transcripts(
    client: httpx.AsyncClient, from_dt: str, to_dt: str
) -> dict[str, list[dict]]:
    transcript_by_id: dict[str, list[dict]] = {}
    cursor: str | None = None
    while True:
        body: dict = {"filter": {"fromDateTime": from_dt, "toDateTime": to_dt}}
        if cursor:
            body["cursor"] = cursor
        resp = await client.post(f"{API_BASE}/v2/calls/transcript", json=body)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        payload = resp.json()
        for entry in payload.get("callTranscripts", []):
            transcript_by_id[entry["callId"]] = entry.get("transcript", [])
        cursor = (payload.get("records") or {}).get("cursor")
        if not cursor:
            break
    return transcript_by_id


async def index_gong(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    allowed_workspace_ids = set(source_service.gong_allowed_workspace_ids(source))
    if not allowed_workspace_ids:
        # Purge anything indexed before the allowlist existed so unscoped
        # transcripts stop being searchable, then fail loudly so the sync
        # records a sync_error instead of reporting a successful no-op.
        await source_service.soft_delete_missing("gong_documents", source_id, [])
        raise RuntimeError("no allowed workspaces configured")

    creds = json.loads(await get_valid_token(owner_user_id, "gong"))
    headers = {"Authorization": basic_auth_header(creds["access_key"], creds["access_key_secret"])}
    to_dt = datetime.now(UTC).isoformat()
    from_dt = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).isoformat()

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        meta_by_id = await _fetch_call_meta(client, from_dt, to_dt)
        transcript_by_id = await _fetch_transcripts(client, from_dt, to_dt)

    present: list[str] = []
    for call_id, meta in meta_by_id.items():
        if _call_workspace_id(meta) not in allowed_workspace_ids:
            continue
        await source_service.upsert_content_document(
            table="gong_documents",
            source_id=source_id,
            workspace_id=workspace_id,
            path=call_id,
            name=meta.get("title") or call_id,
            kind="call",
            content=_render_call(meta, transcript_by_id.get(call_id, [])),
            external_ref=call_id,
        )
        present.append(call_id)

    await source_service.soft_delete_missing("gong_documents", source_id, present)
    logger.info("gong source: indexed %d call(s)", len(present))
    return None


async def fetch_history(source: dict, since, until, limit: int = 500) -> dict:
    """On-demand: pull calls in [since, until] — older than the rolling window
    the scheduled sync keeps. Caches them (upsert) so they're searchable
    afterward, and returns the call ids found. No soft-delete: this adds to the
    cache, it doesn't define the live set."""
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    allowed_workspace_ids = set(source_service.gong_allowed_workspace_ids(source))
    if not allowed_workspace_ids:
        return {
            "fetched": 0,
            "since": since.isoformat(),
            "until": until.isoformat() if until else None,
            "results": [],
        }

    creds = json.loads(await get_valid_token(owner_user_id, "gong"))
    headers = {"Authorization": basic_auth_header(creds["access_key"], creds["access_key_secret"])}
    from_dt = since.isoformat()
    to_dt = (until or datetime.now(UTC)).isoformat()

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        meta_by_id = await _fetch_call_meta(client, from_dt, to_dt)
        transcript_by_id = await _fetch_transcripts(client, from_dt, to_dt)

    refs: list[str] = []
    for call_id, meta in meta_by_id.items():
        if len(refs) >= limit:
            break
        if _call_workspace_id(meta) not in allowed_workspace_ids:
            continue
        await source_service.upsert_content_document(
            table="gong_documents",
            source_id=source_id,
            workspace_id=workspace_id,
            path=call_id,
            name=meta.get("title") or call_id,
            kind="call",
            content=_render_call(meta, transcript_by_id.get(call_id, [])),
            external_ref=call_id,
        )
        refs.append(call_id)

    return {
        "fetched": len(refs),
        "since": since.isoformat(),
        "until": until.isoformat() if until else None,
        "results": [{"ref": r} for r in refs[:25]],
    }
