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

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import settings
from ..services import billing_service, security_audit_service, source_service
from . import storage
from .base import AccountInfo
from .crypto import integration_fernet, integration_keyring_error
from .github import account_sync as github_account_sync
from .registry import get_provider, list_providers
from .slack import indexer as slack_indexer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# How long a `state` blob is valid between /connect and /callback.
STATE_TTL = timedelta(minutes=10)


SLACK_CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
SLACK_CHANNEL_TYPES = "public_channel,private_channel,im,mpim"
SLACK_CHANNEL_LIMIT = 100


def _encode_state(
    user_id: UUID,
    provider: str,
    return_to: str | None = None,
    *,
    extra: dict | None = None,
) -> str:
    payload = json.dumps(
        {
            "u": str(user_id),
            "p": provider,
            "n": secrets.token_urlsafe(16),
            "t": datetime.now(UTC).isoformat(),
            "r": return_to,
            "x": extra or {},
        }
    )
    return integration_fernet().encrypt(payload.encode()).decode()


def _decode_state_payload(state: str, expected_provider: str) -> dict:
    try:
        raw = integration_fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    payload = json.loads(raw)
    if payload.get("p") != expected_provider:
        raise HTTPException(status_code=400, detail="provider mismatch in state")
    return payload


def _decode_state(state: str, expected_provider: str) -> tuple[UUID, str | None]:
    payload = _decode_state_payload(state, expected_provider)
    return UUID(payload["u"]), payload.get("r")


def _safe_return_to(return_to: str | None) -> str | None:
    """Only honor relative same-origin paths; blocks open-redirect."""
    if not return_to or not return_to.startswith("/") or return_to.startswith("//"):
        return None
    return return_to


class IntegrationAccountItem(BaseModel):
    account_key: str
    account_email: str | None = None
    account_display_name: str | None = None
    scopes: list[str]
    expires_at: str | None = None
    connected_at: str | None = None
    needs_reconnect: bool = False
    # Disconnected-with-data-kept: no token, but sources/documents remain.
    disconnected: bool = False


class ProviderListItem(BaseModel):
    provider: str
    display_name: str
    scopes: list[str]
    connected: bool
    # Disconnected-with-data-kept: not connected, but the provider still has
    # sources/documents the user chose to keep.
    disconnected: bool = False
    enabled: bool
    disabled_reason: str | None = None
    # "oauth" (the default redirect flow), "mcp_oauth" (DCR+PKCE via an MCP
    # server, e.g. Granola), or "api_key" (pasted credentials, e.g. Gong).
    auth_kind: str = "oauth"
    # For api_key providers: the form fields the frontend should render.
    credential_fields: list[dict] | None = None
    account_email: str | None = None
    account_display_name: str | None = None
    expires_at: str | None = None
    connected_at: str | None = None
    accounts: list[IntegrationAccountItem] = Field(default_factory=list)


class IntegrationsListResponse(BaseModel):
    providers: list[ProviderListItem]


class SlackChannelSummary(BaseModel):
    id: str
    name: str
    is_private: bool


def _provider_disabled_reason(provider: str) -> str | None:
    keyring_error = integration_keyring_error()
    if keyring_error:
        return keyring_error

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
        "gmail": [
            "GMAIL_OAUTH_CLIENT_ID",
            "GMAIL_OAUTH_CLIENT_SECRET",
            "GMAIL_OAUTH_REDIRECT_URI",
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
        "gong": [
            "GONG_OAUTH_CLIENT_ID",
            "GONG_OAUTH_CLIENT_SECRET",
            "GONG_OAUTH_REDIRECT_URI",
        ],
        "granola": ["GRANOLA_OAUTH_REDIRECT_URI"],
        "x": ["TWITTER_OAUTH_CLIENT_ID", "TWITTER_OAUTH_REDIRECT_URI"],
        "jira": [
            "JIRA_OAUTH_CLIENT_ID",
            "JIRA_OAUTH_CLIENT_SECRET",
            "JIRA_OAUTH_REDIRECT_URI",
        ],
        "linear": [
            "LINEAR_OAUTH_CLIENT_ID",
            "LINEAR_OAUTH_CLIENT_SECRET",
            "LINEAR_OAUTH_REDIRECT_URI",
        ],
        "asana": [
            "ASANA_OAUTH_CLIENT_ID",
            "ASANA_OAUTH_CLIENT_SECRET",
            "ASANA_OAUTH_REDIRECT_URI",
        ],
    }
    missing = [name for name in required.get(provider, []) if not getattr(settings, name)]
    if missing:
        display_names = {
            "github": "GitHub",
            "google": "Google",
            "gmail": "Gmail",
            "notion": "Notion",
            "slack": "Slack",
            "gong": "Gong",
            "x": "X",
            "granola": "Granola",
            "jira": "Jira",
            "linear": "Linear",
            "asana": "Asana",
        }
        display = display_names.get(provider, provider)
        return f"{display} OAuth is not configured for this server. Missing: {', '.join(missing)}"
    return None


def _ensure_provider_enabled(provider: str) -> None:
    disabled_reason = _provider_disabled_reason(provider)
    if disabled_reason:
        raise HTTPException(status_code=503, detail=disabled_reason)


async def _user_may_use_provider(p, user_id: UUID) -> bool:
    """Customer-specific providers declare `allowed_email_domains` (e.g. Heavi);
    providers without it are open to everyone. Allowed = a verified email on
    one of the domains, or being the scope user of a workspace on one — the
    same trust anchor as workspace membership (users.email_verified)."""
    domains = getattr(p, "allowed_email_domains", None)
    if domains is None:
        return True
    from ..database import get_pool

    return bool(
        await get_pool().fetchval(
            "SELECT EXISTS (SELECT 1 FROM users WHERE id = $1 AND email_verified "
            "               AND lower(split_part(email, '@', 2)) = ANY($2::text[])) "
            "    OR EXISTS (SELECT 1 FROM workspaces "
            "               WHERE scope_user_id = $1 AND domain = ANY($2::text[]))",
            user_id,
            list(domains),
        )
    )


@router.get("", response_model=IntegrationsListResponse)
async def list_integrations(current_user: dict = Depends(get_current_user)):
    user_connections = {
        c["provider"]: c for c in await storage.list_connections(current_user["id"])
    }
    items = []
    for p in list_providers():
        if not await _user_may_use_provider(p, current_user["id"]):
            continue
        conn = user_connections.get(p.name)
        disabled_reason = _provider_disabled_reason(p.name)
        items.append(
            ProviderListItem(
                provider=p.name,
                display_name=p.display_name,
                scopes=p.scopes,
                connected=conn is not None and not conn["disconnected"],
                disconnected=bool(conn and conn["disconnected"]),
                enabled=disabled_reason is None,
                disabled_reason=disabled_reason,
                auth_kind=getattr(p, "auth_kind", "oauth"),
                credential_fields=[
                    {
                        "name": f.name,
                        "label": f.label,
                        "secret": f.secret,
                        "placeholder": f.placeholder,
                        "optional": f.optional,
                        "help": f.help,
                    }
                    for f in getattr(p, "credential_fields", [])
                ]
                or None,
                account_email=conn["account_email"] if conn else None,
                account_display_name=conn["account_display_name"] if conn else None,
                expires_at=conn["expires_at"] if conn else None,
                connected_at=conn["connected_at"] if conn else None,
                accounts=conn["accounts"] if conn else [],
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
    if not await _user_may_use_provider(p, current_user["id"]):
        raise HTTPException(
            status_code=403, detail=f"{p.display_name} is not available for your account"
        )
    await billing_service.ensure_can_connect(current_user["id"])
    # MCP OAuth providers (Granola) register a client + carry PKCE through their
    # own state, so they own the connect step end-to-end.
    if getattr(p, "auth_kind", "oauth") == "mcp_oauth":
        url = await p.start_authorization(current_user["id"], _safe_return_to(return_to))
        return ConnectStartResponse(authorize_url=url)
    return_path = _safe_return_to(return_to)
    # PKCE providers (X) carry a per-connect code verifier through the encrypted
    # state so the callback can complete the token exchange.
    if getattr(p, "uses_pkce", False):
        code_verifier = p.new_code_verifier()
        state = _encode_state(
            current_user["id"], provider, return_path, extra={"code_verifier": code_verifier}
        )
        return ConnectStartResponse(authorize_url=p.authorize_url(state, code_verifier))

    state = _encode_state(current_user["id"], provider, return_path)
    return ConnectStartResponse(authorize_url=p.authorize_url(state))


@router.get("/{provider}/callback")
async def integration_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    p = get_provider(provider)
    # The token exchange / account fetch talks to the provider — it can fail for
    # reasons outside our control (bad client secret, provider error, expired
    # code). Surface those as a clean redirect back to the UI with an error flag
    # instead of a bare 500, and log the real cause for debugging.
    try:
        if getattr(p, "auth_kind", "oauth") == "mcp_oauth":
            # The provider owns the exchange + storage and returns where to land.
            return_to = await p.finish_authorization(code, state)
        else:
            payload = _decode_state_payload(state, expected_provider=provider)
            user_id = UUID(payload["u"])
            return_to = payload.get("r")
            if getattr(p, "uses_pkce", False):
                code_verifier = (payload.get("x") or {}).get("code_verifier")
                if not code_verifier:
                    raise HTTPException(status_code=400, detail="missing PKCE verifier in state")
                token = await p.exchange_code(code, code_verifier)
            else:
                token = await p.exchange_code(code)
            # The account profile is display-only — a failure fetching it must
            # NOT block the connection (the token is what matters). Degrade to
            # an empty identity instead.
            try:
                account = await p.fetch_account(token.access_token)
            except Exception as e:
                logger.warning(
                    "fetch_account failed for %s; connecting without profile (%s)",
                    provider,
                    type(e).__name__,
                )
                account = AccountInfo(email=None, display_name=None)
            # Reconnect identity check: refuse to link a DIFFERENT provider
            # account while the previous account's connection (and possibly
            # its kept data) exists. The identity comes from the provider's
            # own answer to the new token — never from the client.
            mismatched = await storage.account_mismatch(user_id, provider, account)
            if mismatched:
                logger.warning(
                    "OAuth callback account mismatch for %s: stored account differs", provider
                )
                base = settings.PUBLIC_URL.rstrip("/")
                query = {"integration_error": "account_mismatch", "expected": mismatched}
                return RedirectResponse(
                    url=f"{base}/integrations/{provider}?{urlencode(query)}", status_code=302
                )
            await storage.store_token(user_id, provider, token, account)
            await security_audit_service.record_user_event(
                action="integration.connected",
                actor_user_id=user_id,
                target_type="integration",
                target_id=provider,
                provider=provider,
                metadata={"auth_kind": getattr(p, "auth_kind", "oauth")},
            )

            # --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
            # Capture the connecting user's Slack identity so the bot can map
            # inbound mentions to this Stash user without relying on email.
            # Best-effort: a failure here must not break the connection.
            if provider == "slack":
                from .slack import links

                try:
                    await links.capture_from_user_token(user_id, token.access_token)
                except Exception as exc:
                    logger.warning(
                        "slack: failed to capture user link exception_type=%s",
                        type(exc).__name__,
                    )
            # --- END Slack agent ---

            # Connecting X auto-creates its x_saves source and records the
            # account id, which the indexer needs to read bookmarks (X API) and
            # the user's own posts/replies (twitterapi.io). Best-effort: a
            # failure here must not break the connection.
            if provider == "x":
                from ..database import get_pool
                from ..services import source_service
                from .x_saves.provider import fetch_me

                try:
                    me = await fetch_me(token.access_token)
                    source = await source_service.create_source(
                        owner_user_id=user_id,
                        source_type="x_saves",
                        external_ref=me["id"],
                        display_name=f"X (@{me.get('username')})" if me.get("username") else "X",
                        settings={},
                    )
                    await get_pool().execute(
                        "UPDATE user_sources SET settings = "
                        "coalesce(settings, '{}'::jsonb) || $2::jsonb WHERE id = $1",
                        UUID(source["id"]),
                        {"x_user_id": me["id"]},
                    )
                except Exception as exc:
                    logger.warning(
                        "x: failed to auto-create source exception_type=%s", type(exc).__name__
                    )
    except HTTPException:
        raise  # already a clean client error (e.g. invalid/expired state → 400)
    except Exception as e:
        logger.warning("OAuth callback failed for provider %s (%s)", provider, type(e).__name__)
        base = settings.PUBLIC_URL.rstrip("/")
        query = {"integration_error": provider, "reason": "connection_failed"}
        return RedirectResponse(url=f"{base}/settings?{urlencode(query)}", status_code=302)

    base = settings.PUBLIC_URL.rstrip("/")
    target = _safe_return_to(return_to) or "/settings"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(
        url=f"{base}{target}{sep}{urlencode({'connected': provider})}",
        status_code=302,
    )


class DisconnectRequest(BaseModel):
    delete_data: bool = False


async def _purge_provider_data(user_id: UUID, provider: str, reason: str) -> list[dict]:
    """Delete a provider's data (sources, documents, media blobs, shares) and
    forget the stored account entirely, so a different account may connect."""
    purged = await source_service.purge_sources_for_provider(user_id, provider)
    await storage.revoke_stored(user_id, provider)
    for source in purged:
        await security_audit_service.record_event(
            action="source.purged",
            actor_user_id=user_id,
            owner_user_id=UUID(source["owner_user_id"]),
            target_type="source",
            target_id=source["id"],
            provider=provider,
            source_type=source["source_type"],
            metadata={"reason": reason},
        )
    return purged


@router.post("/{provider}/disconnect")
async def integration_disconnect(
    provider: str,
    body: DisconnectRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Disconnect stops syncing and revokes credentials; it deletes data ONLY
    when the user explicitly chose that in the disconnect dialog."""
    get_provider(provider)  # 404 if unknown
    delete_data = bool(body and body.delete_data)
    if delete_data:
        removed = await _purge_provider_data(
            current_user["id"], provider, reason="integration_disconnect"
        )
    else:
        removed = await source_service.disable_sources_for_provider(current_user["id"], provider)
        await storage.disconnect_stored(current_user["id"], provider)
    await security_audit_service.record_user_event(
        action="integration.disconnected",
        actor_user_id=current_user["id"],
        target_type="integration",
        target_id=provider,
        provider=provider,
        metadata={"sources": len(removed), "data_deleted": delete_data},
    )
    return {"ok": True, "sources": len(removed), "data_deleted": delete_data}


@router.post("/{provider}/purge")
async def integration_purge(
    provider: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete the kept data of a disconnected (or connected) provider. The
    explicit, destructive counterpart to disconnect-keeps-data. Gated on the
    source-type map, not the OAuth registry — extension-fed providers
    (Instagram) have data to purge but no OAuth provider."""
    if provider not in source_service.PROVIDER_SOURCE_TYPES:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    purged = await _purge_provider_data(current_user["id"], provider, reason="purge")
    return {"ok": True, "sources": len(purged)}


class CredentialConnectResponse(BaseModel):
    connected: bool
    account_email: str | None
    account_display_name: str | None


@router.post("/{provider}/credentials", response_model=CredentialConnectResponse)
async def integration_connect_with_credentials(
    provider: str,
    values: dict[str, str],
    current_user: dict = Depends(get_current_user),
):
    """Connect an api_key provider from pasted credentials.
    The provider validates them against the upstream and returns the bundle as
    the stored token; we never echo the secrets back."""
    p = get_provider(provider)
    _ensure_provider_enabled(provider)
    if getattr(p, "auth_kind", "oauth") != "api_key":
        raise HTTPException(status_code=400, detail=f"{provider} does not use credential auth")
    if not await _user_may_use_provider(p, current_user["id"]):
        raise HTTPException(
            status_code=403, detail=f"{p.display_name} is not available for your account"
        )
    await billing_service.ensure_can_connect(current_user["id"])
    # Both handlers redact the exception message — provider errors can embed
    # the pasted secrets, so only the exception type is logged.
    try:
        token, account = await p.connect_with_credentials(values)
    except ValueError as e:
        logger.warning(
            "Credential connection rejected for provider %s (%s)",
            provider,
            type(e).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect {p.display_name}; check credentials",
        )
    except Exception as e:
        logger.warning(
            "Credential connection failed for provider %s (%s)",
            provider,
            type(e).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect {p.display_name}; upstream unavailable",
        )
    await storage.store_token(current_user["id"], provider, token, account)
    await security_audit_service.record_user_event(
        action="integration.connected",
        actor_user_id=current_user["id"],
        target_type="integration",
        target_id=provider,
        provider=provider,
        metadata={"auth_kind": "api_key"},
    )
    return CredentialConnectResponse(
        connected=True,
        account_email=account.email,
        account_display_name=account.display_name,
    )


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


@router.get("/slack/channels", response_model=list[SlackChannelSummary])
async def slack_list_channels(current_user: dict = Depends(get_current_user)):
    access_token = await storage.get_valid_token(current_user["id"], "slack")
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.get(
            SLACK_CONVERSATIONS_LIST_URL,
            params={"types": SLACK_CHANNEL_TYPES, "limit": SLACK_CHANNEL_LIMIT},
        )
        resp.raise_for_status()
        payload = resp.json()

        if not payload.get("ok"):
            raise HTTPException(
                status_code=502,
                detail=f"Slack API error: {payload.get('error') or 'unknown_error'}",
            )

        # DMs carry no name in Slack's API — resolve them to the humans in the
        # conversation, exactly as the indexer names them, so the picker shows
        # what the source tree will show.
        self_user_id = await slack_indexer.authed_user_id(client)
        names: dict[str, str] = {}
        channels: list[SlackChannelSummary] = []
        for channel in payload.get("channels", []):
            channel_id = channel.get("id")
            if not channel_id:
                continue
            channels.append(
                SlackChannelSummary(
                    id=channel_id,
                    name=await slack_indexer.channel_display_name(
                        client, names, channel, self_user_id
                    ),
                    is_private=bool(channel.get("is_private")),
                )
            )
    return channels


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
    """List every GitHub repo the user can see (most-recently-updated first)
    so the frontend can render a picker instead of asking for a URL."""
    access_token = await storage.get_valid_token(current_user["id"], "github")
    repos = await github_account_sync.list_visible_repos(access_token)

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


class GitHubRepoAccess(BaseModel):
    # "All repositories" mode: every visible repo is kept registered as a
    # github_repo source. total/created are only present right after a PUT
    # that enabled the mode.
    all_repos: bool
    total: int | None = None
    created: int | None = None


class GitHubRepoAccessUpdate(BaseModel):
    all_repos: bool


@router.get("/github/repo-access", response_model=GitHubRepoAccess)
async def github_get_repo_access(current_user: dict = Depends(get_current_user)):
    return GitHubRepoAccess(all_repos=await storage.get_sync_all(current_user["id"], "github"))


@router.put("/github/repo-access", response_model=GitHubRepoAccess)
async def github_set_repo_access(
    body: GitHubRepoAccessUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Switch between all-repos and select-repos mode. Enabling registers a
    source for every visible repo right away; the hourly reconcile keeps the
    set current after that. Disabling stops auto-registration but keeps the
    sources already created."""
    updated = await storage.set_sync_all(current_user["id"], "github", body.all_repos)
    if not updated:
        raise HTTPException(status_code=404, detail="GitHub is not connected")
    await security_audit_service.record_user_event(
        action="integration.repo_access_changed",
        actor_user_id=current_user["id"],
        target_type="integration",
        target_id="github",
        provider="github",
        metadata={"all_repos": body.all_repos},
    )
    if not body.all_repos:
        return GitHubRepoAccess(all_repos=False)
    result = await github_account_sync.sync_all_repos(current_user["id"])
    return GitHubRepoAccess(all_repos=True, total=result["total"], created=result["created"])


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


class JiraProjectSummary(BaseModel):
    # external_ref is "{cloudId}:{projectKey}" — carries the site so the indexer
    # needs no extra lookup.
    external_ref: str
    key: str
    name: str
    site_name: str


@router.get("/jira/projects", response_model=list[JiraProjectSummary])
async def jira_list_projects(current_user: dict = Depends(get_current_user)):
    """List projects across every Atlassian site the user granted us, so the
    frontend can render a picker. Jira REST calls are per-cloudId, so we first
    resolve the accessible sites, then page each site's projects."""
    import httpx

    access_token = await storage.get_valid_token(current_user["id"], "jira")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    out: list[JiraProjectSummary] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        sites_resp = await client.get("https://api.atlassian.com/oauth/token/accessible-resources")
        sites_resp.raise_for_status()
        for site in sites_resp.json():
            cloud_id = site["id"]
            site_name = site.get("name") or cloud_id
            start_at = 0
            while True:
                resp = await client.get(
                    f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project/search",
                    params={"startAt": start_at, "maxResults": 50},
                )
                resp.raise_for_status()
                payload = resp.json()
                for proj in payload.get("values", []):
                    out.append(
                        JiraProjectSummary(
                            external_ref=f"{cloud_id}:{proj['key']}",
                            key=proj["key"],
                            name=proj.get("name") or proj["key"],
                            site_name=site_name,
                        )
                    )
                if payload.get("isLast", True):
                    break
                start_at += payload.get("maxResults", 50)
    return out


class AsanaProjectSummary(BaseModel):
    gid: str
    name: str
    workspace_name: str


@router.get("/asana/projects", response_model=list[AsanaProjectSummary])
async def asana_list_projects(current_user: dict = Depends(get_current_user)):
    """List the user's Asana projects across all their workspaces for the picker.
    external_ref is the project gid."""
    import httpx

    access_token = await storage.get_valid_token(current_user["id"], "asana")
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[AsanaProjectSummary] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        ws_resp = await client.get("https://app.asana.com/api/1.0/workspaces")
        ws_resp.raise_for_status()
        for ws in ws_resp.json().get("data", []):
            resp = await client.get(
                "https://app.asana.com/api/1.0/projects",
                params={"workspace": ws["gid"], "opt_fields": "name", "limit": 100},
            )
            resp.raise_for_status()
            for proj in resp.json().get("data", []):
                out.append(
                    AsanaProjectSummary(
                        gid=proj["gid"],
                        name=proj.get("name") or proj["gid"],
                        workspace_name=ws.get("name") or ws["gid"],
                    )
                )
    return out
