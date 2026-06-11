"""Slack agent (talk-to-Stash bot) — outbound Slack Web API calls.

Mirrors the httpx pattern in indexer.py but for the bot token: post replies
and resolve a Slack user's email. Part of the removable Slack-agent feature.
"""

from __future__ import annotations

import httpx

POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
USERS_INFO_URL = "https://slack.com/api/users.info"


async def post_message(
    bot_token: str, channel: str, text: str, thread_ts: str | None = None
) -> None:
    payload: dict = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            POST_MESSAGE_URL,
            headers={"Authorization": f"Bearer {bot_token}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage error: {data.get('error')}")


async def get_user_email(bot_token: str, slack_user_id: str) -> str | None:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            USERS_INFO_URL,
            headers={"Authorization": f"Bearer {bot_token}"},
            params={"user": slack_user_id},
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack users.info error: {data.get('error')}")
    return ((data.get("user") or {}).get("profile") or {}).get("email")
