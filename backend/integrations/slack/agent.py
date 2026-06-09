"""Slack agent (talk-to-Stash bot) — turn a Slack mention/DM into an agent run.

This is the seam where the Slack surface meets the existing agent: it resolves
the Slack user to a Stash account, runs the workspace agent in that user's
single continuous Slack session, and posts the reply back. Everything agent-
side (tool_loop, tools, memory, scoping) is reused unchanged.

REMOVAL: this module + installs.py + client.py + the provider bot-token
capture + the webhook agent branch + the respond_to_slack_mention Celery task
+ the slack_bot_installs table are the whole feature. Delete them to drop it.
"""

from __future__ import annotations

import logging
import re

from ...services import ask_service, user_service, workspace_service
from . import client, installs

logger = logging.getLogger(__name__)

# Slack renders mentions as <@U123>; strip the bot's own token from the prompt.
_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")

_NO_ACCOUNT_MSG = (
    "I couldn't match your Slack email to a Stash account. "
    "Make sure your Stash account uses the same email as Slack."
)


def _strip_mentions(text: str) -> str:
    return _MENTION_RE.sub("", text).strip()


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

    email = await client.get_user_email(bot_token, slack_user_id)
    user = await user_service.get_user_by_email(email) if email else None
    if user is None:
        await client.post_message(bot_token, channel, _NO_ACCOUNT_MSG, thread_ts)
        return

    workspace_id = await workspace_service.get_primary_for_user(user["id"])
    if workspace_id is None:
        spaces = await workspace_service.list_user_workspaces(user["id"])
        workspace_id = spaces[0]["id"] if spaces else None
    if workspace_id is None:
        await client.post_message(
            bot_token, channel, "You don't have a Stash workspace yet.", thread_ts
        )
        return

    workspace = await workspace_service.get_workspace(workspace_id)
    # One continuous session per user → memory accumulates across DMs/channels/time.
    session_id = f"slack-agent-{user['id']}"
    answer = await ask_service.run_chat(
        workspace_id, workspace["name"], user["id"], session_id, text
    )
    await client.post_message(
        bot_token, channel, answer or "(I didn't produce a response.)", thread_ts
    )
