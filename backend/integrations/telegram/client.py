"""Telegram Bot API client — outbound calls with the platform bot token."""

from __future__ import annotations

import httpx

from ...config import settings

_API = "https://api.telegram.org"


def _base() -> str:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return f"{_API}/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int | str, text: str, *, reply_to: int | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{_base()}/sendMessage", json=payload)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage error: {data.get('description')}")


async def get_me() -> dict:
    """The bot's own identity — used to detect @mentions in groups."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base()}/getMe")
    return resp.json().get("result") or {}


async def set_webhook(url: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_base()}/setWebhook",
            json={
                "url": url,
                "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                "allowed_updates": ["message"],
            },
        )
    return resp.json()
