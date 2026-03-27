"""Deck viewer router: public token-based access to shared decks."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import deck_service

router = APIRouter(prefix="/api/v1/d", tags=["deck_viewer"])


class DeckViewerMeta(BaseModel):
    deck_name: str
    deck_type: str
    require_email: bool
    has_passcode: bool
    allow_download: bool


class DeckVerifyRequest(BaseModel):
    email: str | None = None
    passcode: str | None = None


@router.get("/{token}")
async def get_deck_meta(token: str):
    """Get deck metadata for a share link (no auth required)."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    if share.get("expires_at") and share["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")
    return DeckViewerMeta(
        deck_name=share["deck_name"],
        deck_type=share["deck_type"],
        require_email=share["require_email"],
        has_passcode=share["passcode_hash"] is not None,
        allow_download=share["allow_download"],
    )


@router.get("/{token}/content")
async def get_deck_content(token: str):
    """Get the full HTML content of a shared deck."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    if share.get("expires_at") and share["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")
    # If no gates, return content directly
    if not share["require_email"] and not share.get("passcode_hash"):
        return {
            "html_content": share["html_content"],
            "deck_name": share["deck_name"],
            "deck_type": share["deck_type"],
        }
    # If gates exist, require verification first
    raise HTTPException(status_code=403, detail="Verification required")


@router.post("/{token}/verify")
async def verify_access(token: str, req: DeckVerifyRequest):
    """Verify email/passcode to access a gated deck."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    if share.get("expires_at") and share["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")
    if share.get("passcode_hash") and req.passcode:
        if not await deck_service.verify_passcode(share, req.passcode):
            raise HTTPException(status_code=403, detail="Invalid passcode")
    return {
        "html_content": share["html_content"],
        "deck_name": share["deck_name"],
        "deck_type": share["deck_type"],
    }
