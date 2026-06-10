"""Product telemetry: insert + read analytics_events rows.

This is the lightweight, structured-properties log. Separate from history_events,
which is the agent-transcript log (content-heavy, embedded).
"""

import logging
from collections.abc import Iterable
from uuid import UUID

from ..database import get_pool

logger = logging.getLogger(__name__)

# Surfaces an event can come from. 'system' is reserved for backend-emitted
# rows (e.g. a future signup hook); 'marketing' is the anonymous www
# landing-page beacon (routers/marketing.py). Clients may send 'web'/'cli'.
ALLOWED_SURFACES = {"web", "cli", "system", "marketing"}

# Closed set of event names we accept from clients. Adding a new event means
# adding a row here AND wiring the call site — keeps the dashboard honest.
ALLOWED_EVENT_NAMES = {
    # Onboarding funnel (linear Connect → Ask; no path picker)
    "onboarding.viewed",
    "onboarding.step_viewed",
    "onboarding.source_selected",
    "onboarding.skipped",
    "onboarding.completed",
    # Web actions
    "web.workspace_created",
    "web.page_created",
    "web.page_edited",
    "web.file_uploaded",
    "web.stash_created",
    "web.session_shared",
    "web.search_query",
    "web.ask_cartridge",
    # Auth lifecycle
    "auth.signed_up",
    # CLI commands (one event per invocation; properties.command is the sub-axis)
    "cli.command_invoked",
    # Messaging-test landing pages (anonymous; properties.variant is the axis)
    "marketing.view",
    "marketing.signup",
}


async def record_event(
    *,
    user_id: UUID | str | None,
    surface: str,
    event_name: str,
    properties: dict | None = None,
    session_anon: str | None = None,
) -> None:
    # The pool's jsonb codec (database.py) serializes dicts itself — passing a
    # pre-dumped string here double-encodes and breaks properties->> queries.
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO analytics_events (user_id, surface, event_name, properties, session_anon)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        user_id,
        surface,
        event_name,
        properties or {},
        session_anon,
    )


async def record_events_batch(rows: Iterable[dict]) -> int:
    """Bulk insert. Each row must have surface, event_name; user_id/properties/session_anon optional."""
    payload = [
        (
            r.get("user_id"),
            r["surface"],
            r["event_name"],
            r.get("properties") or {},
            r.get("session_anon"),
        )
        for r in rows
    ]
    if not payload:
        return 0
    pool = get_pool()
    await pool.executemany(
        """
        INSERT INTO analytics_events (user_id, surface, event_name, properties, session_anon)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        payload,
    )
    return len(payload)
