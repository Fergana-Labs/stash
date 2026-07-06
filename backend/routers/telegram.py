"""Telegram connect: mint the deep-link a user taps to bind their Telegram id.

The webhook + agent live elsewhere (webhooks.py, integrations/telegram/); this
is just the in-product "Connect Telegram" action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..config import settings
from ..integrations.telegram import links

router = APIRouter(prefix="/api/v1/me/telegram", tags=["telegram"])


@router.post("/connect-link")
async def connect_link(current_user: dict = Depends(get_current_user)):
    """A one-tap deep link that binds the opener's Telegram account to this user."""
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(status_code=503, detail="Telegram is not configured.")
    code = await links.mint_connect_code(current_user["id"])
    return {"url": f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={code}"}
