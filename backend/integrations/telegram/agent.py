"""Telegram agent (talk-to-Stash bot) — turn a Telegram message into a turn.

Mirrors the Slack agent: resolve the Telegram user to a Stash account, run the
cloud agent in that user's session, post the reply. Behavior:
  - Private chat: reply to every message; one continuous session.
  - Group chat: reply only when the bot is @-mentioned or its message is
    replied to (Fleet responds to all group text; we don't, to avoid noise);
    each group thread is its own session.
"""

from __future__ import annotations

import logging

from ...config import settings
from ...services import sprite_agent_service, user_service
from . import client, links

logger = logging.getLogger(__name__)


def _connect_prompt() -> str:
    url = f"{settings.PUBLIC_URL.rstrip('/')}/settings"
    return (
        "I don't know who you are in Stash yet. Open Stash settings, connect "
        f"Telegram, and tap the link to bind this chat: {url}"
    )


def _text_and_mention(message: dict, bot_username: str | None) -> tuple[str, bool]:
    """The message text, and whether the bot was addressed (mention or reply)."""
    text = message.get("text") or ""
    addressed = False
    reply = message.get("reply_to_message") or {}
    if (reply.get("from") or {}).get("is_bot"):
        addressed = True
    mention = f"@{bot_username}" if bot_username else None
    if mention and mention in text:
        addressed = True
        text = text.replace(mention, "").strip()
    return text.strip(), addressed


async def _handle_start(chat_id: int, telegram_user_id: str, text: str) -> None:
    """`/start <code>` binds this Telegram user to the account that minted the
    code (deep-link connect). Bare `/start` just explains how to connect."""
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    if not code:
        await client.send_message(chat_id, _connect_prompt())
        return
    user_id = await links.redeem_connect_code(code, telegram_user_id)
    if user_id is None:
        await client.send_message(chat_id, "That link expired. Generate a new one in Stash settings.")
        return
    user = await user_service.get_user_by_id(user_id)
    name = (user["display_name"] or user["name"]) if user else "there"
    await client.send_message(chat_id, f"Connected — hi {name}. Ask me anything about your Stash.")


async def respond_to_message(message: dict) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = message.get("from") or {}
    telegram_user_id = str(from_user.get("id")) if from_user.get("id") else None
    text = message.get("text") or ""
    if not chat_id or not telegram_user_id or not text or from_user.get("is_bot"):
        return

    if text.startswith("/start"):
        await _handle_start(chat_id, telegram_user_id, text)
        return

    is_private = chat.get("type") == "private"
    body, addressed = _text_and_mention(message, settings.TELEGRAM_BOT_USERNAME)
    # In groups, only engage when addressed; in DMs, always.
    if not is_private and not addressed:
        return
    if not body:
        return

    user_id = await links.get_linked_user_id(telegram_user_id)
    if user_id is None:
        await client.send_message(chat_id, _connect_prompt())
        return

    user = await user_service.get_user_by_id(user_id)
    if user is None:
        await client.send_message(chat_id, _connect_prompt())
        return

    owner_name = user["display_name"] or user["name"]
    session_id = _session_id(user_id, message, is_private)
    reply_to = message.get("message_id") if not is_private else None
    try:
        answer = await sprite_agent_service.run_chat(user_id, owner_name, user_id, session_id, body)
    except sprite_agent_service.NeedsAuth:
        url = f"{settings.PUBLIC_URL.rstrip('/')}/settings"
        await client.send_message(
            chat_id,
            f"Connect your Claude, Codex, or OpenRouter key — or upgrade to Pro — here: {url}",
            reply_to=reply_to,
        )
        return
    except sprite_agent_service.TurnInProgress:
        await client.send_message(
            chat_id, "I'm still working on your last message — one sec.", reply_to=reply_to
        )
        return
    except Exception:
        logger.exception("telegram agent: turn failed for %s", session_id)
        await client.send_message(
            chat_id, "Something went wrong on that one. Try again?", reply_to=reply_to
        )
        return
    await client.send_message(chat_id, answer or "(I didn't produce a response.)", reply_to=reply_to)


def _session_id(user_id, message: dict, is_private: bool) -> str:
    """DMs are one continuous conversation; each group thread is its own."""
    if is_private:
        return f"telegram-agent-{user_id}-dm"
    thread = message.get("message_thread_id") or (message.get("chat") or {}).get("id")
    return f"telegram-agent-{user_id}-t-{thread}"
