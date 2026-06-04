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


def _encode_state(user_id: UUID, provider: str, return_to: str | None = None) -> str:
    payload = json.dumps(
        {
            "u": str(user_id),
            "p": provider,
            "n": secrets.token_urlsafe(16),
            "t": datetime.now(UTC).isoformat(),
            "r": return_to,
        }
    )
    return _get_state_fernet().encrypt(payload.encode()).decode()


def _decode_state(state: str, expected_provider: str) -> tuple[UUID, str | None]:
    try:
        raw = _get_state_fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    payload = json.loads(raw)
    if payload.get("p") != expected_provider:
        raise HTTPException(status_code=400, detail="provider mismatch in state")
    return UUID(payload["u"]), payload.get("r")


def _safe_return_to(return_to: str | None) -> str | None:
    """Only honor relative same-origin paths; blocks open-redirect."""
    if not return_to or not return_to.startswith("/") or return_to.startswith("//"):
        return None
    return return_to


class ProviderListItem(BaseModel):
    provider: str
    display_name: str
    scopes: list[str]
    connected: bool
    enabled: bool
    disabled_reason: str | None = None
    # "oauth" (the default redirect flow) or "mcp_oauth" (DCR+PKCE via an MCP
    # server, e.g. Granola).
    auth_kind: str = "oauth"
    account_email: str | None = None
    account_display_name: str | None = None
    expires_at: str | None = None
    connected_at: str | None = None


class IntegrationsListResponse(BaseModel):
    providers: list[ProviderListItem]


def _provider_disabled_reason(provider: str) -> str | None:
    if not settings.INTEGRATIONS_ENCRYPTION_KEY:
        return (
            "OAuth integrations are not configured for this server. "
            "Set INTEGRATIONS_ENCRYPTION_KEY to enable them."
        )
    try:
        Fernet(settings.INTEGRATIONS_ENCRYPTION_KEY.encode())
    except ValueError:
        return "INTEGRATIONS_ENCRYPTION_KEY must be a valid Fernet key."

    required: dict[str, list[str]] = {
        "github": [
            "GITHUB_OAUTH_CLIENT_ID",
            "GITHUB_OAUTH_CLIENT_SECRET",
            "GITHUB_OAUTH_REDIRECT_URI",
        ],
        "google": [
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
        ],
        "notion": [
            "NOTION_OAUTH_CLIENT_ID",
            "NOTION_OAUTH_CLIENT_SECRET",
            "NOTION_OAUTH_REDIRECT_URI",
        ],
        "slack": [
            "SLACK_OAUTH_CLIENT_ID",
            "SLACK_OAUTH_CLIENT_SECRET",
            "SLACK_OAUTH_REDIRECT_URI",
        ],
        "granola": ["GRANOLA_OAUTH_REDIRECT_URI"],
    }
    missing = [name for name in required.get(provider, []) if not getattr(settings, name)]
    if missing:
        display_names = {
            "github": "GitHub",
            "google": "Google",
            "notion": "Notion",
            "slack": "Slack",
            "granola": "Granola",
        }
        return f"{display_names.get(provider, provider)} OAuth is not configured for this server."
    return None


def _ensure_provider_enabled(provider: str) -> None:
    disabled_reason = _provider_disabled_reason(provider)
    if disabled_reason:
        raise HTTPException(status_code=503, detail=disabled_reason)


@router.get("", response_model=IntegrationsListResponse)
async def list_integrations(current_user: dict = Depends(get_current_user)):
    user_connections = {
        c["provider"]: c for c in await storage.list_connections(current_user["id"])
    }
    items = []
    for p in list_providers():
        conn = user_connections.get(p.name)
        disabled_reason = _provider_disabled_reason(p.name)
        items.append(
            ProviderListItem(
                provider=p.name,
                display_name=p.display_name,
                scopes=p.scopes,
                connected=conn is not None,
                enabled=disabled_reason is None,
                disabled_reason=disabled_reason,
                auth_kind=getattr(p, "auth_kind", "oauth"),
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
    return_to: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Return the provider's OAuth authorize URL.

    The app uses Bearer-token auth from localStorage — a top-window
    navigation can't carry that header, so we can't 302 here. Instead
    the frontend fetches this with the Bearer, gets the URL, and does
    the navigation itself.

    `return_to`, if a relative same-origin path, is round-tripped through
    the encrypted state so the callback can land the user back where they
    started (e.g. /onboarding) instead of /settings.
    """
    p = get_provider(provider)
    _ensure_provider_enabled(provider)
    # MCP OAuth providers (Granola) register a client + carry PKCE through their
    # own state, so they own the connect step end-to-end.
    if getattr(p, "auth_kind", "oauth") == "mcp_oauth":
        url = await p.start_authorization(current_user["id"], _safe_return_to(return_to))
        return ConnectStartResponse(authorize_url=url)
    state = _encode_state(current_user["id"], provider, _safe_return_to(return_to))
    return ConnectStartResponse(authorize_url=p.authorize_url(state))


@router.get("/{provider}/callback")
async def integration_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    p = get_provider(provider)
    if getattr(p, "auth_kind", "oauth") == "mcp_oauth":
        # The provider owns the exchange + storage and returns where to land.
        return_to = await p.finish_authorization(code, state)
    else:
        user_id, return_to = _decode_state(state, expected_provider=provider)
        token = await p.exchange_code(code)
        account = await p.fetch_account(token.access_token)
        await storage.store_token(user_id, provider, token, account)

    base = settings.PUBLIC_URL.rstrip("/")
    target = _safe_return_to(return_to) or "/settings"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(
        url=f"{base}{target}{sep}{urlencode({'connected': provider})}",
        status_code=302,
    )


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
