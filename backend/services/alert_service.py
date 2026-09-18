"""Operational alerts delivered by the installed Stash Slack bot."""

from __future__ import annotations

import logging

from ..config import settings
from ..integrations.slack import client, installs

logger = logging.getLogger(__name__)


async def send_alert(text: str) -> None:
    logger.error("ALERT: %s", text)
    if not settings.ALERT_SLACK_TEAM_ID or not settings.ALERT_SLACK_CHANNEL_ID:
        raise RuntimeError("ALERT_SLACK_TEAM_ID and ALERT_SLACK_CHANNEL_ID are required")
    install = await installs.get_install(settings.ALERT_SLACK_TEAM_ID)
    if install is None:
        raise RuntimeError("The alert workspace has no Stash Slack bot installation")
    await client.post_message(install["bot_token"], settings.ALERT_SLACK_CHANNEL_ID, text)
