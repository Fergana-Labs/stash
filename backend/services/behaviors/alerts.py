"""Alert rules: tell the owner when a behavior crosses its threshold.

A rule is stored on the behavior as
  {"threshold": <hits>, "window_hours": 24, "cooldown_hours": 24, "channels": ["slack", "email"]}
and fires when the behavior's non-rejected hits in the window reach the
threshold. Every firing is recorded (the in-app list) and delivered to the
owner directly: a Slack DM from the Stash bot when they linked Slack, and an
email when they have an address. One rule fires at most once per cooldown.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from ...config import settings
from ...database import get_pool

log = logging.getLogger(__name__)

DEFAULT_WINDOW_HOURS = 24
DEFAULT_COOLDOWN_HOURS = 24
CHANNELS = ("slack", "email")


def normalize(rule: dict | None) -> dict | None:
    if not rule:
        return None
    threshold = int(rule.get("threshold") or 0)
    if threshold < 1:
        raise ValueError("An alert threshold must be at least 1 hit")
    window = int(rule.get("window_hours") or DEFAULT_WINDOW_HOURS)
    cooldown = int(rule.get("cooldown_hours") or DEFAULT_COOLDOWN_HOURS)
    if not (1 <= window <= 24 * 30) or not (1 <= cooldown <= 24 * 30):
        raise ValueError("Alert windows and cooldowns are between 1 hour and 30 days")
    channels = [c for c in rule.get("channels") or list(CHANNELS) if c in CHANNELS]
    return {
        "threshold": threshold,
        "window_hours": window,
        "cooldown_hours": cooldown,
        "channels": channels,
    }


def message(behavior: dict, count: int, traces: int, window: int) -> str:
    link = f"{settings.PUBLIC_URL.rstrip('/')}/reward-models/behaviors/{behavior['id']}"
    return (
        f"Behavior alert: “{behavior['name']}” happened {count} times in {traces} "
        f"traces over the last {window}h (threshold {behavior['alert']['threshold']}). {link}"
    )


async def _slack(owner_id: UUID, text: str) -> bool:
    from ...integrations.slack import client, installs

    link = await get_pool().fetchrow(
        "SELECT team_id, slack_user_id FROM slack_user_links WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
        owner_id,
    )
    if link is None:
        return False
    install = await installs.get_install(link["team_id"])
    if install is None:
        return False
    await client.post_message(install["bot_token"], link["slack_user_id"], text)
    return True


async def _email(owner_id: UUID, behavior: dict, text: str) -> bool:
    from .. import email_service

    address = await get_pool().fetchval("SELECT email FROM users WHERE id = $1", owner_id)
    if not address or not settings.POSTMARK_SERVER_TOKEN:
        return False
    payload = {
        "From": email_service.DEFAULT_FROM,
        "To": address,
        "Subject": f"Behavior alert: {behavior['name']}",
        "TextBody": text,
    }
    await asyncio.to_thread(email_service._send, payload)
    return True


async def deliver(behavior: dict, text: str) -> list[str]:
    delivered = []
    channels = behavior["alert"].get("channels") or list(CHANNELS)
    for name, send in (
        ("slack", lambda: _slack(behavior["owner_user_id"], text)),
        ("email", lambda: _email(behavior["owner_user_id"], behavior, text)),
    ):
        if name not in channels:
            continue
        try:
            if await send():
                delivered.append(name)
        except Exception as exc:  # A failed channel must not block the others or the record.
            log.warning("Behavior alert delivery over %s failed: %s", name, type(exc).__name__)
    return delivered


async def evaluate() -> int:
    """Fire every alert rule that is over threshold and out of cooldown."""
    pool = get_pool()
    due = await pool.fetch(
        """SELECT b.*, s.hits, s.traces FROM behaviors b
           CROSS JOIN LATERAL (
             SELECT count(*)::int AS hits, count(DISTINCT h.trace_id)::int AS traces
             FROM behavior_hits h
             WHERE h.behavior_id = b.id AND h.review IS DISTINCT FROM 'rejected'
               AND h.created_at > now() - make_interval(hours => (b.alert->>'window_hours')::int)
           ) s
           WHERE b.enabled AND b.alert IS NOT NULL
             AND s.hits >= (b.alert->>'threshold')::int
             AND (b.last_alert_at IS NULL
                  OR b.last_alert_at < now() - make_interval(hours => (b.alert->>'cooldown_hours')::int))"""
    )
    for row in due:
        behavior = dict(row)
        # Claim the firing first, so overlapping ticks cannot alert twice.
        claimed = await pool.fetchval(
            """UPDATE behaviors SET last_alert_at = now() WHERE id = $1
               AND (last_alert_at IS NULL OR last_alert_at < now() - make_interval(hours => (alert->>'cooldown_hours')::int))
               RETURNING id""",
            behavior["id"],
        )
        if claimed is None:
            continue
        window = behavior["alert"]["window_hours"]
        text = message(behavior, behavior["hits"], behavior["traces"], window)
        delivered = await deliver(behavior, text)
        await pool.execute(
            "INSERT INTO behavior_alerts (behavior_id, owner_user_id, message, stats, delivered) VALUES ($1, $2, $3, $4, $5)",
            behavior["id"], behavior["owner_user_id"], text,
            {"hits": behavior["hits"], "traces": behavior["traces"], "window_hours": window}, delivered,
        )  # fmt: skip
    return len(due)


async def recent(owner_id: UUID, limit: int = 50) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT a.*, b.name AS behavior_name FROM behavior_alerts a JOIN behaviors b ON b.id = a.behavior_id
           WHERE a.owner_user_id = $1 ORDER BY a.created_at DESC LIMIT $2""",
        owner_id,
        limit,
    )
    return [dict(r) for r in rows]
