"""Slack agent (talk-to-Stash bot) — turn a Slack mention/DM into an agent run.

This is the seam where the Slack surface meets the existing agent: it resolves
the Slack user to a Stash account, runs the scope agent in that user's
single continuous Slack session, and posts the reply back. Everything agent-
side (tool_loop, tools, memory, scoping) is reused unchanged.

REMOVAL: this module + installs.py + client.py + links.py + the provider
bot-token capture + the router link capture + the webhook agent branch + the
respond_to_slack_mention Celery task + the slack_bot_installs / slack_user_links
tables are the whole feature. Delete them to drop it.
"""

from __future__ import annotations

import logging
import re

from ...config import settings
from ...services import ask_service, user_scope_service, user_service
from . import client, installs, links

logger = logging.getLogger(__name__)

# Slack renders mentions as <@U123>; strip the bot's own token from the prompt.
_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")


def _strip_mentions(text: str) -> str:
    return _MENTION_RE.sub("", text).strip()


def _connect_prompt() -> str:
    """Shown when we can't map the Slack user to a Stash account — points them
    at the in-product Slack connect, which captures the link (and wires up their
    Slack source)."""
    url = f"{settings.PUBLIC_URL.rstrip('/')}/settings"
    return (
        "I don't know who you are in Stash yet. Connect Slack from your Stash "
        f"settings and I'll link you automatically: {url}"
    )


async def _resolve_stash_user(team_id: str, slack_user_id: str, bot_token: str) -> dict | None:
    """Map a Slack user to a Stash account. Primary: the link captured at connect
    time. Fallback: email match, which then self-heals by writing the link."""
    user_id = await links.get_linked_user_id(team_id, slack_user_id)
    if user_id is not None:
        return await user_service.get_user_by_id(user_id)

    email = await client.get_user_email(bot_token, slack_user_id)
    user = await user_service.get_user_by_email(email) if email else None
    if user is not None:
        await links.store_link(team_id, slack_user_id, user["id"])
    return user


async def respond_to_mention(team_id: str, event: dict) -> None:
    install = await installs.get_install(team_id)
    if install is None:
        logger.info("slack agent: no bot install for team %s", team_id)
        return

    bot_token = install["bot_token"]
    slack_user_id = event.get("user")
    channel = event.get("channel")
    # Keep the conversation in-thread (fall back to the message ts itself).
    thread_ts = event.get("thread_ts") or event.get("ts")
    text = _strip_mentions(event.get("text") or "")
    if not slack_user_id or not channel or not text:
        return

    user = await _resolve_stash_user(team_id, slack_user_id, bot_token)
    if user is None:
        await client.post_message(bot_token, channel, _connect_prompt(), thread_ts)
        return

    owner_user_id = await user_scope_service.scope_id_for_user(user["id"])
    # The scope is the user, so its name is the user's display name.
    owner_name = user["display_name"] or user["name"]
    # One continuous session per user → memory accumulates across DMs/channels/time.
    session_id = f"slack-agent-{user['id']}"
    answer = await ask_service.run_chat(
        owner_user_id, owner_name, user["id"], session_id, text
    )
    await client.post_message(
        bot_token, channel, answer or "(I didn't produce a response.)", thread_ts
    )
