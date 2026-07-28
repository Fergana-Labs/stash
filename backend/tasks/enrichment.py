"""Enrichment reconciliation: fill LLM-derived table columns.

Beat-scheduled alongside the embedding reconciler, and deliberately the same
shape: rows carry `enrich_stale`, a sweep claims a batch, and `enrich_hash`
stops unchanged rows being re-enriched (an import that re-runs must not pay
for the same rows twice).

Failure is terminal per row, not per batch: a row that can't be enriched
records `enrich_error` and clears its flag. A poison row would otherwise be
re-selected forever and wedge every sweep behind it.

Label vocabulary is the reason this isn't a pure per-row function. Asking a
model for free-form topics on each row independently yields "AI agents",
"agentic AI", and "LLM agents" as three labels. So the multiselect column's
existing `options` are fed back in as the preferred vocabulary, and any
genuinely new label is appended to it — the column is both the output and
the dictionary, which converges instead of drifting.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services import llm, table_service
from ..services.mini_program_service import KIND_LABELS, KIND_SUMMARY
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

BATCH_SIZE = 8
# ~600 tokens of source text. Summaries and topics only need the opening of an
# article, and this is the single biggest lever on enrichment cost.
MAX_SOURCE_CHARS = 2400

# Bootstrap: propose a starting vocabulary from a sample of titles before any
# row is labelled. Without it the first rows are labelled against an empty
# vocabulary, so each one invents its own labels and there is nothing to
# converge on — five saves produced eighteen near-synonymous topics in testing.
# Titles alone are enough to name a library's themes, and cost almost nothing.
BOOTSTRAP_MIN_ROWS = 5
BOOTSTRAP_SAMPLE = 40
BOOTSTRAP_TARGET_LABELS = 16

SYSTEM_PROMPT = (
    "You label saved content for a personal library. You are given one item's "
    "metadata and the start of its text. Reply with JSON only — no prose, no "
    "code fences."
)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _page_text(clip_url: str | None, owner_user_id: UUID) -> str:
    """Resolve a Clip cell (an app URL for a page or file) to its stored text.

    Link-only bookmarks have no clip, and a clip whose page was deleted has
    no text; both yield "" and the model works from metadata alone.
    """
    if not clip_url:
        return ""
    tail = clip_url.rstrip("/").rsplit("/", 2)[-2:]
    if len(tail) != 2:
        return ""
    kind, ref = tail
    try:
        ref_id = UUID(ref)
    except ValueError:
        return ""
    pool = get_pool()
    if kind == "p":
        row = await pool.fetchrow(
            "SELECT content_markdown, content_html FROM pages "
            "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
            ref_id,
            owner_user_id,
        )
        if not row:
            return ""
        return row["content_markdown"] or row["content_html"] or ""
    if kind == "f":
        return (
            await pool.fetchval(
                "SELECT extracted_text FROM files "
                "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
                ref_id,
                owner_user_id,
            )
            or ""
        )
    return ""


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


async def _source_text(row_data: dict, config: dict, owner_user_id: UUID) -> str:
    parts = [
        str(row_data.get(col_id, "")).strip()
        for col_id in config.get("context_columns", [])
        if row_data.get(col_id)
    ]
    body = _strip_html(await _page_text(row_data.get(config.get("page_column")), owner_user_id))
    if body:
        parts.append(body)
    return "\n".join(parts)[:MAX_SOURCE_CHARS]


def _build_prompt(source: str, targets: list[dict], vocabulary: list[str]) -> str:
    asks: list[str] = []
    shape: dict[str, str] = {}
    for target in targets:
        if target["kind"] == KIND_SUMMARY:
            asks.append(f'- "summary": {target.get("instruction", "One or two sentences.")}')
            shape["summary"] = "<string>"
        elif target["kind"] == KIND_LABELS:
            vocab = ", ".join(vocabulary) if vocabulary else "(none yet)"
            asks.append(
                f'- "topics": up to {target.get("max", 4)} short topic labels.\n'
                f"  Existing labels in this library: {vocab}\n"
                "  Reuse an existing label whenever it fits — only invent a new "
                "one when none of them describes the item. Title Case, 1-3 words."
            )
            shape["topics"] = "[<string>, ...]"
    return (
        f"Item:\n{source}\n\n"
        f"Return JSON with these fields:\n" + "\n".join(asks) + "\n\n"
        f"Shape: {json.dumps(shape)}"
    )


def _labels_column(columns: list[dict], col_id: str) -> dict | None:
    return next((c for c in columns if c["id"] == col_id), None)


async def _vocabulary(table_id: UUID, col_id: str) -> list[str]:
    """The labels column's current options, read fresh from the table."""
    columns = await get_pool().fetchval("SELECT columns FROM tables WHERE id = $1", table_id)
    column = _labels_column(columns or [], col_id)
    return list((column or {}).get("options") or [])


async def _merge_vocabulary(table_id: UUID, col_id: str, new_labels: list[str]) -> None:
    """Append genuinely new labels to the multiselect column's options, so the
    next row's prompt sees them and reuses them. Shared with manual tag edits,
    which must feed the same vocabulary."""
    await table_service.merge_column_options(table_id, col_id, new_labels)


def _coerce(payload: dict, targets: list[dict]) -> tuple[dict, list[str]]:
    """Map the model's JSON onto column ids. Returns (cell updates, new labels)."""
    updates: dict[str, object] = {}
    labels: list[str] = []
    for target in targets:
        if target["kind"] == KIND_SUMMARY:
            summary = str(payload.get("summary") or "").strip()
            if summary:
                updates[target["column"]] = summary
        elif target["kind"] == KIND_LABELS:
            raw = payload.get("topics") or []
            if isinstance(raw, str):
                raw = [raw]
            labels = [str(t).strip() for t in raw if str(t).strip()][: target.get("max", 4)]
            if labels:
                updates[target["column"]] = labels
    return updates, labels


async def _bootstrap_vocabulary(table_id: UUID, config: dict, columns: list[dict]) -> None:
    """Seed a labels column's options from a sample of the table's own titles.

    Runs at most once per table in practice: it only fires while the column's
    options are still empty, and the first enriched row fills them. One
    QUALITY-tier call buys every later row a vocabulary to reuse.
    """
    target = next((t for t in config.get("targets", []) if t["kind"] == KIND_LABELS), None)
    if target is None:
        return
    column = _labels_column(columns, target["column"])
    if column is None or (column.get("options") or []):
        return

    context_columns = config.get("context_columns") or []
    if not context_columns:
        return
    rows = await get_pool().fetch(
        "SELECT data FROM table_rows WHERE table_id = $1 ORDER BY row_order LIMIT $2",
        table_id,
        BOOTSTRAP_SAMPLE,
    )
    titles = [
        str(row["data"].get(context_columns[0], "")).strip()
        for row in rows
        if row["data"].get(context_columns[0])
    ]
    if len(titles) < BOOTSTRAP_MIN_ROWS:
        return

    listed = "\n".join(f"- {t}" for t in titles)
    try:
        payload = await llm.complete_json(
            prompt=(
                f"Here are titles of items in one person's saved library:\n{listed}\n\n"
                f"Propose up to {BOOTSTRAP_TARGET_LABELS} topic labels that would file "
                "this library well. Prefer broad themes a person would browse by over "
                "labels specific to one item, and merge near-synonyms into one label. "
                'Title Case, 1-3 words each. Return JSON: {"topics": [<string>, ...]}'
            ),
            system=SYSTEM_PROMPT,
            tier=llm.ModelTier.QUALITY,
            max_tokens=500,
        )
    except Exception as e:  # noqa: BLE001 - bootstrap is an optimisation, not a gate
        logger.warning("vocabulary bootstrap failed for table %s: %s", table_id, e)
        return

    labels = [str(t).strip() for t in (payload.get("topics") or []) if str(t).strip()]
    if labels:
        await _merge_vocabulary(table_id, target["column"], labels[:BOOTSTRAP_TARGET_LABELS])


async def _claim_batch() -> list[dict]:
    """Take rows off the queue atomically.

    Clearing `enrich_stale` here — not in `_settle` — is what makes this a
    claim. A plain SELECT left rows flagged for the whole model call, and a
    batch takes longer than the beat interval, so the next sweep re-selected
    the same rows and paid for them again. FOR UPDATE SKIP LOCKED keeps
    concurrent workers off each other's rows.

    A worker that dies mid-batch leaves its rows claimed but unenriched; they
    stay visible with no summary and can be requeued from the detail pane.
    """
    rows = await get_pool().fetch(
        "UPDATE table_rows tr SET enrich_stale = FALSE "
        "FROM tables t "
        "WHERE t.id = tr.table_id AND tr.id IN ("
        "  SELECT tr2.id FROM table_rows tr2 JOIN tables t2 ON t2.id = tr2.table_id "
        "  WHERE tr2.enrich_stale "
        "    AND t2.enrichment_config IS NOT NULL "
        "    AND (t2.enrichment_config->>'enabled')::boolean "
        "  ORDER BY tr2.id FOR UPDATE OF tr2 SKIP LOCKED LIMIT $1"
        ") "
        "RETURNING tr.id, tr.data, tr.table_id, tr.updated_at, tr.enrich_hash, "
        "          t.owner_user_id, t.enrichment_config, t.columns",
        BATCH_SIZE,
    )
    return [dict(r) for r in rows]


async def _settle(row_id: UUID, *, hash_: str | None = None, error: str | None = None) -> None:
    """Record the outcome. The row already left the queue at claim time."""
    await get_pool().execute(
        "UPDATE table_rows SET enrich_hash = $1, enrich_error = $2 WHERE id = $3",
        hash_,
        error,
        row_id,
    )


async def _apply_updates(row: dict, updates: dict, digest: str) -> bool:
    """Write model output only if the row did not change during the model call.

    A generic row edit changes updated_at. If only source cells changed, queue
    a fresh pass so the summary matches the new content. If a derived cell was
    edited, the manual value wins and the row stays settled.
    """
    applied = await get_pool().fetchval(
        "UPDATE table_rows "
        "SET data = data || $1, embed_stale = TRUE, enrich_hash = $2, enrich_error = NULL "
        "WHERE id = $3 AND updated_at = $4 "
        "RETURNING TRUE",
        updates,
        digest,
        row["id"],
        row["updated_at"],
    )
    if applied:
        return True

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            current = await conn.fetchval(
                "SELECT data FROM table_rows WHERE id = $1 FOR UPDATE",
                row["id"],
            )
            if current is None:
                return False

            target_columns = {target["column"] for target in row["enrichment_config"]["targets"]}
            manual_target_edit = any(
                current.get(column) != row["data"].get(column) for column in target_columns
            )
            if manual_target_edit:
                await conn.execute(
                    "UPDATE table_rows SET enrich_hash = $1, enrich_error = NULL WHERE id = $2",
                    digest,
                    row["id"],
                )
                return False

            await conn.execute(
                "UPDATE table_rows SET enrich_stale = TRUE WHERE id = $1",
                row["id"],
            )
    return False


async def _enrich_row(row: dict) -> bool:
    """Enrich one row. Returns True if the model was called."""
    config = row["enrichment_config"]
    targets = config.get("targets") or []
    if not targets:
        await _settle(row["id"], error="table has no enrichment targets")
        return False

    source = await _source_text(row["data"], config, row["owner_user_id"])
    if not source:
        await _settle(row["id"], error="no source text to enrich from")
        return False

    digest = _content_hash(source)
    if digest == row["enrich_hash"]:
        await _settle(row["id"], hash_=digest)
        return False

    label_target = next((t for t in targets if t["kind"] == KIND_LABELS), None)
    vocabulary: list[str] = []
    if label_target:
        # Read fresh rather than from the claim snapshot: the bootstrap pass
        # and earlier rows in this same batch may have just added labels, and
        # reusing those is the whole point.
        vocabulary = await _vocabulary(row["table_id"], label_target["column"])

    try:
        payload = await llm.complete_json(
            prompt=_build_prompt(source, targets, vocabulary),
            system=SYSTEM_PROMPT,
            tier=llm.ModelTier.FAST,
            max_tokens=400,
        )
    except Exception as e:  # noqa: BLE001 - recorded on the row, not swallowed
        logger.warning("enrichment failed for row %s: %s", row["id"], e)
        await _settle(row["id"], error=f"model call failed: {e}")
        return False

    updates, new_labels = _coerce(payload, targets)
    if not updates:
        await _settle(row["id"], error="model returned no usable fields")
        return False

    if label_target and new_labels:
        await _merge_vocabulary(row["table_id"], label_target["column"], new_labels)

    return await _apply_updates(row, updates, digest)


async def _reconcile() -> int:
    rows = await _claim_batch()
    if not rows:
        return 0
    # Seed each table's vocabulary before labelling any of its rows, so the
    # first batch has something to converge on instead of inventing labels
    # row by row. No-ops once the column has options.
    for table_id in {row["table_id"] for row in rows}:
        sample = next(row for row in rows if row["table_id"] == table_id)
        await _bootstrap_vocabulary(table_id, sample["enrichment_config"], sample["columns"])

    # Rows in a batch are independent model calls, so run them concurrently:
    # serially a batch took longer than the beat interval, which is what made
    # a 10k import an overnight job. Vocabulary convergence is unaffected —
    # it accrues across batches, not within one.
    results = await asyncio.gather(*(_enrich_row(row) for row in rows), return_exceptions=True)
    for row, result in zip(rows, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("enrichment crashed for row %s: %s", row["id"], result)
            await _settle(row["id"], error=f"enrichment crashed: {result}")
    return sum(1 for r in results if r is True)


@celery.task(name="backend.tasks.enrichment.reconcile")
def reconcile() -> int:
    return run_async(_reconcile())
