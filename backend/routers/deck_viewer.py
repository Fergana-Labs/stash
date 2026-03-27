"""Deck viewer router: public token-based access with viewer tracking."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
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


class DeckHeartbeatRequest(BaseModel):
    session_token: str
    page_identifier: str | None = None


def _check_expiry(share: dict) -> None:
    if share.get("expires_at"):
        exp = share["expires_at"]
        if hasattr(exp, "tzinfo") and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share link has expired")


@router.get("/{token}")
async def get_deck_meta(token: str):
    """Get deck metadata for a share link (no auth required)."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    _check_expiry(share)
    return DeckViewerMeta(
        deck_name=share["deck_name"],
        deck_type=share["deck_type"],
        require_email=share["require_email"],
        has_passcode=share["passcode_hash"] is not None,
        allow_download=share["allow_download"],
    )


@router.get("/{token}/content")
async def get_deck_content(token: str, request: Request):
    """Get HTML content. No gates → returns directly + creates view session."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    _check_expiry(share)

    if share["require_email"] or share.get("passcode_hash"):
        raise HTTPException(status_code=403, detail="Verification required")

    # Create anonymous view session
    viewer_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    view = await deck_service.create_view_session(
        share["id"], viewer_ip=viewer_ip, user_agent=user_agent,
    )
    return {
        "html_content": share["html_content"],
        "deck_name": share["deck_name"],
        "deck_type": share["deck_type"],
        "session_token": view["session_token"],
    }


@router.post("/{token}/verify")
async def verify_access(token: str, req: DeckVerifyRequest, request: Request):
    """Verify email/passcode gate and create viewer session."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or inactive")
    _check_expiry(share)

    if share.get("passcode_hash") and req.passcode:
        if not await deck_service.verify_passcode(share, req.passcode):
            raise HTTPException(status_code=403, detail="Invalid passcode")
    elif share.get("passcode_hash") and not req.passcode:
        raise HTTPException(status_code=403, detail="Passcode required")

    # Create view session with email
    viewer_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    view = await deck_service.create_view_session(
        share["id"], viewer_email=req.email,
        viewer_ip=viewer_ip, user_agent=user_agent,
    )
    return {
        "html_content": share["html_content"],
        "deck_name": share["deck_name"],
        "deck_type": share["deck_type"],
        "session_token": view["session_token"],
    }


@router.post("/{token}/heartbeat")
async def viewer_heartbeat(token: str, req: DeckHeartbeatRequest):
    """Update viewer session duration and track page engagement."""
    await deck_service.heartbeat(req.session_token, req.page_identifier)
    return {"status": "ok"}


@router.get("/{token}/download")
async def download_html(token: str):
    """Download deck as HTML file (if allowed)."""
    share = await deck_service.get_share_by_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")
    _check_expiry(share)
    if not share["allow_download"]:
        raise HTTPException(status_code=403, detail="Downloads disabled for this share")
    from fastapi.responses import Response
    return Response(
        content=share["html_content"],
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{share["deck_name"]}.html"'},
    )
