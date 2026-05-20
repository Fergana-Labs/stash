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
        c["provider"]: c for c in await storage.list_connections(current_user["id"])
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


class ConnectStartResponse(BaseModel):
    authorize_url: str


@router.get("/{provider}/connect", response_model=ConnectStartResponse)
async def integration_connect(
    provider: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the provider's OAuth authorize URL.

    The app uses Bearer-token auth from localStorage — a top-window
    navigation can't carry that header, so we can't 302 here. Instead
    the frontend fetches this with the Bearer, gets the URL, and does
    the navigation itself.
    """
    p = get_provider(provider)
    state = _encode_state(current_user["id"], provider)
    return ConnectStartResponse(authorize_url=p.authorize_url(state))


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

    # Send the user back to /settings — the Integrations section is
    # embedded there. The query param triggers the panel to re-fetch
    # connection state.
    redirect_target = f"{settings.PUBLIC_URL.rstrip('/')}/settings"
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


class GooglePickerTokenResponse(BaseModel):
    access_token: str
    api_key: str | None  # GOOGLE_PICKER_API_KEY (browser API key)
    app_id: str | None  # GOOGLE_PICKER_APP_ID (GCP project number)


@router.get("/google/picker-token", response_model=GooglePickerTokenResponse)
async def google_picker_token(current_user: dict = Depends(get_current_user)):
    """Hand the frontend a fresh Google access token plus the picker's
    `api_key` and `app_id` so the user's browser can open the Drive
    Picker without exposing our OAuth client secret. Throws 401 if the
    user hasn't connected Google yet — the frontend should send them to
    /settings/integrations first."""
    access_token = await storage.get_valid_token(current_user["id"], "google")
    return GooglePickerTokenResponse(
        access_token=access_token,
        api_key=settings.GOOGLE_PICKER_API_KEY,
        app_id=settings.GOOGLE_PICKER_APP_ID,
    )


class GitHubRepoSummary(BaseModel):
    full_name: str
    description: str | None
    private: bool
    html_url: str
    updated_at: str | None


@router.get("/github/repos", response_model=list[GitHubRepoSummary])
async def github_list_repos(
    current_user: dict = Depends(get_current_user),
    q: str = Query("", description="Substring filter on repo full_name"),
):
    """List the user's GitHub repos (most-recently-updated first) so the
    frontend can render a picker instead of asking the user to paste a URL."""
    import httpx

    access_token = await storage.get_valid_token(current_user["id"], "github")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            params={
                "per_page": 100,
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        resp.raise_for_status()
        repos = resp.json()

    q_lower = q.lower().strip()
    out: list[GitHubRepoSummary] = []
    for r in repos:
        if q_lower and q_lower not in r["full_name"].lower():
            continue
        out.append(
            GitHubRepoSummary(
                full_name=r["full_name"],
                description=r.get("description"),
                private=r.get("private", False),
                html_url=r["html_url"],
                updated_at=r.get("updated_at"),
            )
        )
    return out


class NotionPageSummary(BaseModel):
    id: str
    title: str
    url: str
    icon: str | None
    last_edited_time: str | None


@router.get("/notion/pages", response_model=list[NotionPageSummary])
async def notion_list_pages(
    current_user: dict = Depends(get_current_user),
    q: str = Query("", description="Substring search across page titles"),
):
    """Search Notion pages the integration has access to. Notion only
    returns pages the user has explicitly shared with the integration —
    this matches Notion's own behavior."""
    import httpx

    access_token = await storage.get_valid_token(current_user["id"], "notion")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    body: dict = {
        "filter": {"property": "object", "value": "page"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "page_size": 50,
    }
    if q.strip():
        body["query"] = q.strip()
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.post("https://api.notion.com/v1/search", json=body)
        resp.raise_for_status()
        results = resp.json().get("results", [])

    out: list[NotionPageSummary] = []
    for p in results:
        # Title can live in properties.title (DB pages) or properties.Name (workspace pages).
        title = ""
        props = p.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                break
        if not title:
            title = "(untitled)"
        icon_obj = p.get("icon") or {}
        icon = icon_obj.get("emoji") if icon_obj.get("type") == "emoji" else None
        out.append(
            NotionPageSummary(
                id=p["id"],
                title=title,
                url=p.get("url", ""),
                icon=icon,
                last_edited_time=p.get("last_edited_time"),
            )
        )
    return out
