"""The online loop: keep every enabled behavior's hits current as traces arrive and grow.

Each tick syncs searchable segments for recently changed traces, then runs each
enabled behavior over the traces it has not seen at their current version.
`behavior_scans` records what a behavior has read: a rule rescans the whole
trace (it is free), a model detector reads only segments it has not read
before, a few per pass, until the trace is done. Editing a behavior bumps its
version, which drops its unreviewed hits and rescans from scratch.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ...database import get_pool
from . import builtin, detect, segments

log = logging.getLogger(__name__)

SEGMENT_SYNC_BATCH = 40
SCAN_BATCH = 30
RECENT_DAYS = 30
MODEL_RECENT_DAYS = 7

DONE, PARTIAL, NO_LABELS, FAILED = "done", "partial", "no_labels", "failed"


async def _labels(trace_id: UUID) -> dict[str, dict] | None:
    row = await get_pool().fetchrow(
        "SELECT labels FROM rm_step_labels WHERE trace_id = $1", trace_id
    )
    return None if row is None else row["labels"]


async def _segments(trace_id: UUID) -> list[dict]:
    """The trace's segments, synced first when the trace changed since they were cut."""
    pool = get_pool()
    stale = await pool.fetchrow(
        """SELECT t.owner_user_id FROM rm_traces t WHERE t.id = $1 AND NOT EXISTS (
             SELECT 1 FROM rm_trace_segments s WHERE s.trace_id = t.id AND s.updated_at >= t.updated_at)""",
        trace_id,
    )
    if stale is not None:
        await segments.sync(trace_id, stale["owner_user_id"])
    rows = await pool.fetch(
        "SELECT start_idx, end_idx, text, content_hash FROM rm_trace_segments WHERE trace_id = $1 ORDER BY start_idx",
        trace_id,
    )
    return [dict(r) for r in rows]


async def _store(behavior: dict, trace_id: UUID, hits: list[dict], *, replace: bool) -> int:
    async with get_pool().acquire() as conn, conn.transaction():
        if replace:
            # Reviewed hits are human judgments and outlive any rescan.
            await conn.execute(
                "DELETE FROM behavior_hits WHERE behavior_id = $1 AND trace_id = $2 AND source = 'auto' AND review IS NULL",
                behavior["id"],
                trace_id,
            )
        added = 0
        for hit in hits:
            status = await conn.execute(
                """INSERT INTO behavior_hits
                     (behavior_id, owner_user_id, trace_id, start_idx, end_idx, confidence, evidence, note, detector_version)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (behavior_id, trace_id, start_idx, end_idx) DO NOTHING""",
                behavior["id"], behavior["owner_user_id"], trace_id, hit["start_idx"], hit["end_idx"],
                hit["confidence"], hit["evidence"], hit.get("note", "")[:400], behavior["version"],
            )  # fmt: skip
            added += status.endswith("1")
    return added


async def _record(
    behavior: dict, trace_id: UUID, state: str, seen: list[str], error: str | None = None
):
    await get_pool().execute(
        """INSERT INTO behavior_scans (behavior_id, trace_id, behavior_version, fingerprint, seen, error)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (behavior_id, trace_id) DO UPDATE SET
             behavior_version = EXCLUDED.behavior_version, fingerprint = EXCLUDED.fingerprint,
             seen = EXCLUDED.seen, error = EXCLUDED.error, scanned_at = now()""",
        behavior["id"], trace_id, behavior["version"], state, seen, error,
    )  # fmt: skip


async def scan_trace(behavior: dict, trace_id: UUID, previous: dict | None = None) -> dict:
    """Run one behavior over one trace; returns {"state", "added"}."""
    fresh = previous is None or previous["behavior_version"] != behavior["version"]
    if behavior["detector"] == "rule":
        rule = behavior["rule"] or {}
        labels = await _labels(trace_id) if builtin.needs_labels(rule) else {}
        if labels is None:
            await _record(behavior, trace_id, NO_LABELS, [])
            return {"state": NO_LABELS, "added": 0}
        steps = await segments.read_steps(trace_id)
        added = await _store(behavior, trace_id, builtin.detect(rule, labels, steps), replace=True)
        await _record(behavior, trace_id, DONE, [])
        return {"state": DONE, "added": added}

    segs = await _segments(trace_id)
    seen = set() if fresh else set(previous.get("seen") or [])
    if behavior["detector"] == "agent_judge":
        from ..agent_judge import windows

        hits, read = await windows.detect(behavior, trace_id, segs, seen)
    else:
        hits, read = await detect.detect(behavior, segs, seen)
    added = await _store(behavior, trace_id, hits, replace=fresh)
    current = {s["content_hash"] for s in segs}
    state = DONE if current <= read else PARTIAL
    # Forget hashes of segments the trace no longer has, so `seen` cannot grow without bound.
    await _record(behavior, trace_id, state, sorted(read & current))
    return {"state": state, "added": added}


async def due(models: bool, limit: int | None = None) -> list[dict]:
    """(behavior, trace) pairs whose scan is missing or older than the trace, its labels, or the behavior."""
    rows = await get_pool().fetch(
        """SELECT b.id AS behavior_id, t.id AS trace_id,
                  sc.behavior_version, sc.seen, sc.fingerprint
           FROM behaviors b
           JOIN rm_traces t ON t.owner_user_id = b.owner_user_id
           LEFT JOIN behavior_scans sc ON sc.behavior_id = b.id AND sc.trace_id = t.id
           LEFT JOIN rm_step_labels l ON l.trace_id = t.id
           WHERE b.enabled AND (b.detector <> 'rule') = $4
             AND t.updated_at > now() - make_interval(days => CASE WHEN b.detector = 'rule' THEN $2::int ELSE $3::int END)
             AND t.updated_at < now() - interval '15 seconds'
             AND (sc.trace_id IS NULL
                  OR sc.behavior_version <> b.version
                  OR sc.fingerprint = 'partial'
                  OR (sc.scanned_at < t.updated_at AND sc.fingerprint <> 'failed')
                  OR (sc.fingerprint = 'failed' AND sc.scanned_at < now() - interval '1 hour')
                  OR (l.labeled_at IS NOT NULL AND sc.scanned_at < l.labeled_at AND b.detector = 'rule'))
           ORDER BY t.updated_at DESC
           LIMIT $1""",
        limit or SCAN_BATCH,
        RECENT_DAYS,
        MODEL_RECENT_DAYS,
        models,
    )
    return [dict(r) for r in rows]


async def get_behavior(behavior_id: UUID) -> dict | None:
    row = await get_pool().fetchrow("SELECT * FROM behaviors WHERE id = $1", behavior_id)
    return None if row is None else dict(row)


async def _scan_due(models: bool) -> dict:
    scanned = added = 0
    cache: dict[UUID, dict | None] = {}
    for pair in await due(models):
        if pair["behavior_id"] not in cache:
            cache[pair["behavior_id"]] = await get_behavior(pair["behavior_id"])
        behavior = cache[pair["behavior_id"]]
        if behavior is None:
            continue
        previous = None if pair["behavior_version"] is None else pair
        try:
            result = await scan_trace(behavior, pair["trace_id"], previous)
        except Exception as exc:  # One provider failure must not stall every other pair.
            log.warning("Behavior scan failed: %s", type(exc).__name__)
            await _record(
                behavior, pair["trace_id"], FAILED, list(pair.get("seen") or []), str(exc)[:500]
            )
            continue
        scanned += 1
        added += result["added"]
    return {"scanned": scanned, "added": added}


async def reconcile() -> dict:
    """The cheap tick: segments, rule behaviors, alerts. Reports whether model scans are due."""
    stale = await segments.stale_traces(SEGMENT_SYNC_BATCH, RECENT_DAYS)
    for row in stale:
        await segments.sync(row["id"], row["owner_user_id"])
    result = await _scan_due(models=False)
    from . import alerts

    fired = await alerts.evaluate()
    from ..intuition import alerts as eval_alerts

    fired += await eval_alerts.evaluate()
    return {
        "segments": len(stale),
        **result,
        "alerts": fired,
        "models_due": bool(await due(True, 1)),
    }


MODEL_LOCK = 0x6265_6876  # "behv": one model scan pass at a time across workers


async def scan_models() -> dict:
    """Model-detected behaviors: minutes of provider calls, so they run off the beat queue."""
    async with get_pool().acquire() as conn:
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", MODEL_LOCK):
            return {"skipped": "another pass is running"}
        try:
            return await _scan_due(models=True)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", MODEL_LOCK)
