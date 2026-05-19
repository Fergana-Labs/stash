"""Provider-agnostic OAuth router.

Same handlers serve every registered provider — the provider is resolved
by URL segment. To add a new provider you only need to register it; this
router stays the same.

State handling: the `state` parameter passed to the provider is a Fernet
token carrying `{user_id, provider, nonce}`. The callback decrypts it to
both (a) recover the user identity (the callback URL is hit by the
browser without auth headers) and (b) verify the request originated
here. Fernet's HMAC gives us CSRF protection for free.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..config import settings
from . import storage
from .registry import get_provider, list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# How long a `state` blob is valid between /connect and /callback.
STATE_TTL = timedelta(minutes=10)


def _get_state_fernet() -> Fernet:
    if not settings.INTEGRATIONS_ENCRYPTION_KEY:
        raise HTTPException(
            status_code=500,
            detail="INTEGRATIONS_ENCRYPTION_KEY is not set",
        )
    return Fernet(settings.INTEGRATIONS_ENCRYPTION_KEY.encode())


def _encode_state(user_id: UUID, provider: str) -> str:
    payload = json.dumps(
        {
            "u": str(user_id),
            "p": provider,
            "n": secrets.token_urlsafe(16),
            "t": datetime.now(UTC).isoformat(),
        }
    )
    return _get_state_fernet().encrypt(payload.encode()).decode()


def _decode_state(state: str, expected_provider: str) -> UUID:
    try:
        raw = _get_state_fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    payload = json.loads(raw)
    if payload.get("p") != expected_provider:
        raise HTTPException(status_code=400, detail="provider mismatch in state")
    return UUID(payload["u"])


class ProviderListItem(BaseModel):
    provider: str
    display_name: str
    scopes: list[str]
    connected: bool
    account_email: str | None = None
    account_display_name: str | None = None
    expires_at: str | None = None
    connected_at: str | None = None


class IntegrationsListResponse(BaseModel):
    providers: list[ProviderListItem]


@router.get("", response_model=IntegrationsListResponse)
async def list_integrations(current_user: dict = Depends(get_current_user)):
    user_connections = {
        c["provider"]: c
        for c in await storage.list_connections(current_user["id"])
    }
    items = []
    for p in list_providers():
        conn = user_connections.get(p.name)
        items.append(
            ProviderListItem(
                provider=p.name,
                display_name=p.display_name,
                scopes=p.scopes,
                connected=conn is not None,
                account_email=conn["account_email"] if conn else None,
                account_display_name=conn["account_display_name"] if conn else None,
                expires_at=conn["expires_at"] if conn else None,
                connected_at=conn["connected_at"] if conn else None,
            )
        )
    return IntegrationsListResponse(providers=items)


@router.get("/{provider}/status")
async def integration_status(
    provider: str,
    current_user: dict = Depends(get_current_user),
):
    get_provider(provider)  # 404 if unknown
    return await storage.status(current_user["id"], provider)


@router.get("/{provider}/connect")
async def integration_connect(
    provider: str,
    current_user: dict = Depends(get_current_user),
):
    p = get_provider(provider)
    state = _encode_state(current_user["id"], provider)
    return RedirectResponse(url=p.authorize_url(state), status_code=302)


@router.get("/{provider}/callback")
async def integration_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    p = get_provider(provider)
    user_id = _decode_state(state, expected_provider=provider)

    token = await p.exchange_code(code)
    account = await p.fetch_account(token.access_token)
    await storage.store_token(user_id, provider, token, account)

    # Send the user back to the frontend integrations settings page.
    redirect_target = f"{settings.PUBLIC_URL.rstrip('/')}/settings/integrations"
    query = urlencode({"connected": provider})
    return RedirectResponse(url=f"{redirect_target}?{query}", status_code=302)


@router.post("/{provider}/disconnect")
async def integration_disconnect(
    provider: str,
    current_user: dict = Depends(get_current_user),
):
    get_provider(provider)  # 404 if unknown
    await storage.revoke_stored(current_user["id"], provider)
    return {"ok": True}
