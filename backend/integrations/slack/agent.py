"""Slack agent (talk-to-Stash bot) — turn a Slack mention/DM into an agent run.

This is the seam where the Slack surface meets the existing agent: it resolves
the Slack user to a Stash account, runs the cloud agent (Claude Code on the
user's sprite — see sprite_agent_service) in that user's single continuous
Slack session, and posts the reply back.

REMOVAL: this module + installs.py + client.py + links.py + the provider
bot-token capture + the router link capture + the webhook agent branch + the
respond_to_slack_mention Celery task + the slack_bot_installs / slack_user_links
tables are the whole feature. Delete them to drop it.
"""

from __future__ import annotations

import logging
import re

from ...config import settings
from ...services import sprite_agent_service, user_service
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

    owner_user_id = user["id"]
    # The scope is the user, so its name is the user's display name.
    owner_name = user["display_name"] or user["name"]
    session_id = _session_id(user["id"], event)
    try:
        answer = await sprite_agent_service.run_chat(
            owner_user_id, owner_name, user["id"], session_id, text
        )
    except sprite_agent_service.NeedsAuth:
        await client.post_message(bot_token, channel, _upgrade_prompt(), thread_ts)
        return
    except sprite_agent_service.TurnInProgress:
        await client.post_message(
            bot_token, channel, "I'm still working on your last message — one sec.", thread_ts
        )
        return
    except Exception:
        logger.exception("slack agent: turn failed for %s", session_id)
        await client.post_message(
            bot_token, channel, "Something went wrong on that one. Try again?", thread_ts
        )
        return
    await client.post_message(
        bot_token, channel, answer or "(I didn't produce a response.)", thread_ts
    )


def _upgrade_prompt() -> str:
    url = f"{settings.PUBLIC_URL.rstrip('/')}/settings"
    return (
        "Connect your Claude, Codex, or OpenRouter key — or upgrade to Pro for "
        f"the managed agent — in Stash settings: {url}"
    )


def _session_id(user_id, event: dict) -> str:
    """DMs are one continuous conversation; each channel @-mention thread is its
    own session, so a passing mention doesn't drag in the user's DM history."""
    if event.get("channel_type") == "im":
        return f"slack-agent-{user_id}-dm"
    thread = event.get("thread_ts") or event.get("ts")
    return f"slack-agent-{user_id}-t-{thread}"
