"""Ops alerts for failures an operator must see.

Every alert is logged at ERROR. When ALERT_SLACK_WEBHOOK_URL is set, the
alert is also posted to the team Slack channel; a failed post raises, so a
broken webhook is itself loud instead of silently eating alerts.
"""

from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


async def send_alert(text: str) -> None:
    logger.error("ALERT: %s", text)
    if not settings.ALERT_SLACK_WEBHOOK_URL:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.ALERT_SLACK_WEBHOOK_URL, json={"text": text})
        response.raise_for_status()
