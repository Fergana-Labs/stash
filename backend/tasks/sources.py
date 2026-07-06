"""Source sync orchestration.

`reconcile_due` (Beat) finds pull sources whose scheduled sync is due and
dispatches `sync_source` for each. `sync_source` loads the source, runs the
indexer registered for its type, and records sync status. Indexers crawl the
upstream and upsert into the per-integration tables (idempotent — content-hash
dedupe + soft-delete of vanished paths).

Push sources (Slack/Granola) stream via webhooks and don't appear here; their
periodic safety re-backfill, if any, registers an indexer like the pull types.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from ..celery_app import celery
from ..integrations.asana.indexer import index_asana
from ..integrations.github.indexer import index_github_repo
from ..integrations.gmail.indexer import index_gmail
from ..integrations.gong.indexer import index_gong
from ..integrations.google.indexer import index_google_drive
from ..integrations.granola.indexer import index_granola
from ..integrations.jira.indexer import index_jira
from ..integrations.linear.indexer import index_linear
from ..integrations.notion.indexer import index_notion
from ..integrations.slack.indexer import index_slack, ingest_slack_message
from ..services import source_service
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

SYNC_FAILED_MESSAGE = "Source sync failed; check server logs"

# source_type -> indexer. Each returns the new sync cursor (or None).
INDEXERS: dict[str, Callable[[dict], Awaitable[str | None]]] = {
    "github_repo": index_github_repo,
    "gmail": index_gmail,
    "google_drive": index_google_drive,
    "notion": index_notion,
    "slack": index_slack,
    "granola": index_granola,
    "jira_project": index_jira,
    "asana_project": index_asana,
    "linear": index_linear,
    "gong_calls": index_gong,
}


async def _sync_source(source_id: UUID) -> dict:
    source = await source_service.get_source_for_sync(source_id)
    if source is None:
        return {"status": "gone"}
    indexer = INDEXERS.get(source["source_type"])
    if indexer is None:
        logger.warning("no indexer registered for source type %s", source["source_type"])
        return {"status": "no_indexer"}

    await source_service.mark_sync_started(source_id)
    try:
        cursor = await indexer(source)
    except Exception as exc:
        logger.error(
            "source sync failed source=%s source_type=%s exception_type=%s",
            source_id,
            source["source_type"],
            type(exc).__name__,
            exc_info=True,
        )
        await source_service.mark_sync_failed(source_id, SYNC_FAILED_MESSAGE)
        return {"status": "failed"}
    await source_service.mark_sync_done(source_id, cursor)
    return {"status": "done"}


async def _reconcile_due() -> int:
    due = await source_service.due_sources()
    dispatched = 0
    for s in due:
        if s["source_type"] not in INDEXERS:
            continue
        celery.send_task(
            "backend.tasks.sources.sync_source",
            kwargs={"source_id": s["id"]},
        )
        dispatched += 1
    return dispatched


@celery.task(name="backend.tasks.sources.sync_source")
def sync_source(source_id: str) -> dict:
    return run_async(_sync_source(UUID(source_id)))


@celery.task(name="backend.tasks.sources.reconcile_due")
def reconcile_due() -> int:
    return run_async(_reconcile_due())


@celery.task(name="backend.tasks.sources.ingest_slack_event")
def ingest_slack_event(team_id: str, event: dict) -> int:
    """Upsert a single Slack Events-API message (enqueued by the webhook)."""
    return run_async(ingest_slack_message(team_id, event))


# --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
@celery.task(name="backend.tasks.sources.respond_to_slack_mention")
def respond_to_slack_mention(team_id: str, event: dict) -> None:
    """Run the agent for a Slack @mention / DM and post the reply (enqueued by
    the webhook). Imported lazily so the agent surface stays self-contained."""
    from ..integrations.slack.agent import respond_to_mention

    run_async(respond_to_mention(team_id, event))


# --- END Slack agent ---


# --- BEGIN Telegram agent (talk-to-Stash bot) — removable feature block ---
@celery.task(name="backend.tasks.sources.respond_to_telegram_message")
def respond_to_telegram_message(message: dict) -> None:
    """Run the agent for a Telegram message and post the reply (enqueued by the
    webhook). Imported lazily so the agent surface stays self-contained."""
    from ..integrations.telegram.agent import respond_to_message

    run_async(respond_to_message(message))


# --- END Telegram agent ---
