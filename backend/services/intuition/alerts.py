"""Eval alerts: tell the owner when production stops agreeing with their judge.

A rule is stored on the eval as
  {"min_agreement": 0.8, "min_feedback": 5, "window_days": 7, "cooldown_hours": 24, "channels": [...]}
and fires when the judge's agreement with production feedback (human labels,
outcomes, downstream signals) over the window falls below min_agreement.
It is the online-scorer alarm: the rubric is going stale, refine it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ...config import settings
from ...database import get_pool
from ..behaviors.alerts import CHANNELS, deliver
from .feedback import TRUTH_ORDER_SQL
from .monitoring import _predicted

log = logging.getLogger(__name__)


def normalize(rule: dict | None) -> dict | None:
    if not rule:
        return None
    floor = float(rule.get("min_agreement", 0.8))
    if not 0 < floor <= 1:
        raise ValueError("min_agreement is a share between 0 and 1")
    return {
        "min_agreement": floor,
        "min_feedback": max(1, int(rule.get("min_feedback", 5))),
        "window_days": max(1, min(60, int(rule.get("window_days", 7)))),
        "cooldown_hours": max(1, min(720, int(rule.get("cooldown_hours", 24)))),
        "channels": [c for c in rule.get("channels") or list(CHANNELS) if c in CHANNELS],
    }


async def set_rule(owner_id: UUID, model_id: UUID, rule: dict | None) -> dict | None:
    rule = normalize(rule)
    status = await get_pool().execute(
        "UPDATE intuition_models SET alert = $3 WHERE id = $1 AND owner_user_id = $2",
        model_id,
        owner_id,
        rule,
    )
    if status.endswith(" 0"):
        raise LookupError("Eval not found")
    return rule


async def agreement(model_id: UUID, days: int) -> tuple[int, int]:
    """(calls with feedback, calls whose decision matched it) over the window."""
    rows = await get_pool().fetch(
        f"""SELECT p.output, (SELECT f.label FROM intuition_feedback f WHERE f.prediction_id = p.id AND f.label IS NOT NULL
                               ORDER BY {TRUTH_ORDER_SQL}, f.created_at DESC LIMIT 1) AS truth
            FROM intuition_predictions p
            WHERE p.model_id = $1 AND p.created_at > now() - make_interval(days => $2)""",
        model_id,
        days,
    )
    graded = [r for r in rows if r["truth"] is not None]
    matched = sum(_predicted(r["output"] or {}) == r["truth"] for r in graded)
    return len(graded), matched


async def evaluate() -> int:
    pool = get_pool()
    models = await pool.fetch(
        """SELECT id, owner_user_id, name, alert FROM intuition_models
           WHERE alert IS NOT NULL
             AND (last_alert_at IS NULL OR last_alert_at < now() - make_interval(hours => (alert->>'cooldown_hours')::int))"""
    )
    fired = 0
    for m in models:
        rule = m["alert"]
        n, k = await agreement(m["id"], rule["window_days"])
        if n < rule["min_feedback"] or k / n >= rule["min_agreement"]:
            continue
        claimed = await pool.fetchval(
            """UPDATE intuition_models SET last_alert_at = now() WHERE id = $1
               AND (last_alert_at IS NULL OR last_alert_at < now() - make_interval(hours => (alert->>'cooldown_hours')::int))
               RETURNING id""",
            m["id"],
        )
        if claimed is None:
            continue
        link = f"{settings.PUBLIC_URL.rstrip('/')}/reward-models/evals/{m['id']}"
        text = (
            f"Eval alert: “{m['name']}” agreed with production feedback on {k}/{n} calls "
            f"({k / n:.0%}) over the last {rule['window_days']} days, below {rule['min_agreement']:.0%}. "
            f"Its rubric may be going stale; refine it: {link}"
        )
        await deliver({"owner_user_id": m["owner_user_id"], "alert": rule}, text)
        fired += 1
    return fired
