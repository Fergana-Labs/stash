"""OAuth connect flows for the agent's harness credentials (Claude, Codex).

Both use the public CLI OAuth clients (whose redirect URIs we don't control),
so both are "paste the code" flows: we build a PKCE authorize URL, the user
approves at the provider, copies the code the provider then displays, and we
exchange it. The PKCE verifier rides an encrypted, self-expiring `state` blob
(no server-side session), so the flow is stateless across workers — the same
pattern as Granola's OAuth.

The resulting token becomes a `kind="oauth"` credential in agent_auth, which
materializes it as the CLI's credential file on the sprite (Claude:
~/.claude/.credentials.json + CLAUDE_CONFIG_DIR; Codex: ~/.codex/auth.json).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from ..integrations.crypto import integration_fernet
from . import agent_auth

STATE_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class OAuthProvider:
    provider: str  # the agent_auth provider key
    client_id: str
    authorize: str
    token: str
    redirect: str
    scope: str
    # Provider-specific leading authorize params (order matters for Claude).
    extra: dict[str, str] = field(default_factory=dict)


# The real, public Claude Code CLI OAuth client (subscription login).
CLAUDE = OAuthProvider(
    provider="anthropic",
    client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    authorize="https://claude.com/cai/oauth/authorize",
    token="https://platform.claude.com/v1/oauth/token",
    redirect="https://platform.claude.com/oauth/code/callback",
    scope=(
        "org:create_api_key user:profile user:inference "
        "user:sessions:claude_code user:mcp_servers user:file_upload"
    ),
    extra={"code": "true"},  # Claude wants code=true first, state last.
)

# The real, public Codex CLI OAuth client (ChatGPT login).
CODEX = OAuthProvider(
    provider="openai",
    client_id="app_EMoamEEZ73f0CkXaXp7hrann",
    authorize="https://auth.openai.com/oauth/authorize",
    token="https://auth.openai.com/oauth/token",
    redirect="http://localhost:1455/auth/callback",
    scope="openid profile email offline_access",
    extra={
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "prompt": "login",
    },
)

_BY_PROVIDER = {p.provider: p for p in (CLAUDE, CODEX)}


def get(provider: str) -> OAuthProvider:
    if provider not in _BY_PROVIDER:
        raise HTTPException(status_code=400, detail=f"no OAuth flow for {provider}")
    return _BY_PROVIDER[provider]


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


def _encode_state(user_id: UUID, provider: str, verifier: str) -> str:
    payload = {"u": str(user_id), "p": provider, "v": verifier}
    return integration_fernet().encrypt(json.dumps(payload).encode()).decode()


def _decode_state(state: str) -> dict:
    try:
        raw = integration_fernet().decrypt(state.encode(), ttl=int(STATE_TTL.total_seconds()))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    return json.loads(raw)


def start(user_id: UUID, provider: str) -> dict:
    """Return the authorize URL + the state to pass back to finish()."""
    cfg = get(provider)
    verifier, challenge = _pkce()
    state = _encode_state(user_id, provider, verifier)
    # Order matters for Claude: extra (code=true) first, state last.
    params = {
        **cfg.extra,
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect,
        "scope": cfg.scope,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return {"authorize_url": f"{cfg.authorize}?{httpx.QueryParams(params)}", "state": state}


def _parse_pasted_code(raw: str) -> tuple[str, str | None]:
    """The user may paste a bare code, `code#state`, or the whole redirect URL."""
    raw = raw.strip()
    if "://" in raw:
        q = parse_qs(urlparse(raw).query)
        return (q.get("code", [""])[0], q.get("state", [None])[0])
    if "#" in raw:
        code, _, state = raw.partition("#")
        return code.strip(), state.strip() or None
    return raw, None


async def finish(user_id: UUID, provider: str, pasted: str, state: str) -> None:
    """Exchange the pasted code for tokens and store the OAuth credential."""
    cfg = get(provider)
    code, code_state = _parse_pasted_code(pasted)
    if not code:
        raise HTTPException(status_code=400, detail="no code in the pasted value")
    payload = _decode_state(code_state or state)
    if payload["p"] != provider or payload["u"] != str(user_id):
        raise HTTPException(status_code=400, detail="state does not match this connection")

    token = await _exchange(cfg, code, code_state or state, payload["v"])
    secret = _credential_blob(cfg, token)
    await agent_auth.store_credential(user_id, provider, "oauth", secret)


async def _exchange(cfg: OAuthProvider, code: str, state: str, verifier: str) -> dict:
    # These endpoints take a JSON body, not form-encoded.
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "state": state,
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(cfg.token, json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"token exchange failed: {resp.text[:200]}")
    return resp.json()


def _credential_blob(cfg: OAuthProvider, token: dict) -> str:
    """The secret we store — shaped so agent_auth materializes the right file."""
    if cfg is CLAUDE:
        expires_in = int(token.get("expires_in") or 3600)
        return json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": token.get("access_token"),
                    "refreshToken": token.get("refresh_token") or "",
                    "expiresAt": int(time.time() * 1000) + expires_in * 1000,
                    "scopes": (token.get("scope") or cfg.scope).split(),
                    "subscriptionType": "max",
                }
            }
        )
    # Codex: store the token set; agent_auth wraps it into ~/.codex/auth.json.
    account_id = _jwt_account_id(token.get("id_token"))
    return json.dumps(
        {
            "access_token": token.get("access_token"),
            "id_token": token.get("id_token"),
            "refresh_token": token.get("refresh_token"),
            "account_id": account_id,
        }
    )


def _jwt_account_id(id_token: str | None) -> str:
    """Pull chatgpt_account_id from the id_token (decoded WITHOUT verification —
    display/routing only, never trusted for auth)."""
    if not id_token or id_token.count(".") != 2:
        return ""
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return ""
    auth = claims.get("https://api.openai.com/auth") or {}
    return auth.get("chatgpt_account_id") or claims.get("sub") or ""
