"""Resolve which harness + credentials a user's cloud agent runs on.

The rule (mirrors Fleet's resolveUserKey, adapted to per-user sprites):

  1. Bring-your-own: the user connected Claude Code or Codex (API key or
     OAuth) → run THAT harness with THEIR credential. Backend holds nothing.
  2. Managed: no BYO credential but Pro → opencode on OpenRouter (GLM 5.2),
     billed to us. No Anthropic key involved.
  3. Neither: raise NeedsAuth — connect a key or upgrade.

Local dev short-circuits to the machine's own harness login (no injection).

Credential injection differs by kind:
  - api_key → an env var the CLI reads (ANTHROPIC_API_KEY / OPENAI_API_KEY).
  - oauth   → a credential FILE the CLI reads, written to the box before the
     turn (Claude: ~/.claude/.credentials.json + CLAUDE_CONFIG_DIR; Codex:
     ~/.codex/auth.json). The CLI refreshes the token in that file itself —
     and the provider rotates the refresh token when it does — so the file is
     read back after the turn and stored (save_refreshed). Without that, the
     next turn would overwrite the box with a spent refresh token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from ..config import settings
from ..database import get_pool
from ..integrations.storage import _decrypt, _encrypt
from . import billing_service, model_provider
from . import harness as harness_mod


class NeedsAuth(Exception):
    """The user has no connected agent credential and isn't on a managed tier."""


class ProviderNotConfigured(Exception):
    """The managed provider (OpenRouter) has no key configured on the server."""


# provider a user connects → the harness it drives.
_PROVIDER_HARNESS = {
    "anthropic": harness_mod.CLAUDE,  # Claude Code
    "openai": harness_mod.CODEX,  # Codex
    "openrouter": harness_mod.OPENCODE,  # opencode on the user's OpenRouter key
}
# OpenRouter has no OAuth — API key only.
_API_KEY_ONLY = {"openrouter"}

# The managed agent: opencode driving OpenRouter's GLM 5.2, on our key.
MANAGED_HARNESS = harness_mod.OPENCODE

# OpenRouter load-balances GLM across many third-party hosts, each with its own
# data policy. data_collection "deny" makes OpenRouter route only to providers
# that neither retain nor train on prompts — the basis of the no-training
# guarantee we give customers, so it must ride on every managed turn.
_OPENCODE_PRIVACY_CONFIG = json.dumps(
    {
        "provider": {
            "openrouter": {
                "models": {
                    MANAGED_HARNESS.default_model: {
                        "options": {"provider": {"data_collection": "deny"}}
                    }
                }
            }
        }
    }
)


@dataclass(frozen=True)
class OAuthFile:
    """The on-box credential file an OAuth harness reads, and rewrites when it
    refreshes the token mid-turn."""

    user_id: UUID
    provider: str
    path: str


@dataclass
class RunAuth:
    harness: harness_mod.Harness
    env: dict[str, str] = field(default_factory=dict)
    # Files to write on the box before the turn: {path: contents}. For OAuth.
    files: dict[str, str] = field(default_factory=dict)
    # Set for a stored OAuth credential: the file to read back after the turn.
    oauth_file: OAuthFile | None = None


async def _get_credential(user_id: UUID, provider: str | None = None) -> dict | None:
    """The user's connected credential. With `provider`, only that one (so an
    agent's model override selects a specific connected harness)."""
    if provider is not None:
        row = await get_pool().fetchrow(
            "SELECT provider, kind, secret_enc FROM user_agent_credentials "
            "WHERE user_id = $1 AND provider = $2",
            user_id,
            provider,
        )
    else:
        row = await get_pool().fetchrow(
            "SELECT provider, kind, secret_enc FROM user_agent_credentials "
            "WHERE user_id = $1 ORDER BY created_at LIMIT 1",
            user_id,
        )
    if row is None:
        return None
    return {
        "user_id": user_id,
        "provider": row["provider"],
        "kind": row["kind"],
        "secret": _decrypt(row["secret_enc"]),
    }


async def store_credential(user_id: UUID, provider: str, kind: str, secret: str) -> None:
    if provider not in _PROVIDER_HARNESS:
        raise ValueError(f"unknown provider: {provider}")
    if kind not in ("api_key", "oauth"):
        raise ValueError(f"unknown credential kind: {kind}")
    if kind == "oauth" and provider in _API_KEY_ONLY:
        raise ValueError(f"{provider} does not support OAuth")
    await get_pool().execute(
        "INSERT INTO user_agent_credentials (user_id, provider, kind, secret_enc) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (user_id, provider) DO UPDATE "
        "SET kind = EXCLUDED.kind, secret_enc = EXCLUDED.secret_enc, created_at = now()",
        user_id,
        provider,
        kind,
        _encrypt(secret),
    )


async def list_connected(user_id: UUID) -> list[str]:
    rows = await get_pool().fetch(
        "SELECT provider FROM user_agent_credentials WHERE user_id = $1", user_id
    )
    return [r["provider"] for r in rows]


async def delete_credential(user_id: UUID, provider: str) -> None:
    await get_pool().execute(
        "DELETE FROM user_agent_credentials WHERE user_id = $1 AND provider = $2",
        user_id,
        provider,
    )


async def resolve(user_id: UUID, prefer_provider: str | None = None) -> RunAuth:
    """The harness + credential injection for this user's next turn.

    `prefer_provider` is an agent's model override: if the user has that
    provider's credential, run it; a managed OpenRouter preference on Pro uses
    the managed GLM. Falls back to the user's default resolution otherwise.
    """
    # Local dev: the machine's own harness login; inject nothing.
    if settings.AGENT_EXEC_MODE == "local":
        return RunAuth(harness=harness_mod.CLAUDE)

    if prefer_provider:
        cred = await _get_credential(user_id, prefer_provider)
        if cred is not None:
            return _byo_auth(cred)
        # Preferred managed OpenRouter with no BYO key → managed GLM (Pro gate).
        if prefer_provider == "openrouter":
            return await _managed(user_id)
        # The agent explicitly picked a model the user hasn't connected — fail
        # loud rather than silently running a different harness.
        raise NeedsAuth

    cred = await _get_credential(user_id)
    if cred is not None:
        return _byo_auth(cred)
    return await _managed(user_id)


async def _managed(user_id: UUID) -> RunAuth:
    """The managed agent: opencode on OpenRouter GLM, Pro only."""
    if not await billing_service.is_pro(user_id):
        raise NeedsAuth
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise ProviderNotConfigured
    return RunAuth(
        harness=MANAGED_HARNESS,
        env={model_provider.OPENROUTER.env_var: key},
        files={f"{_SPRITE_HOME}/.config/opencode/opencode.json": _OPENCODE_PRIVACY_CONFIG},
    )


def _byo_auth(cred: dict) -> RunAuth:
    harness = _PROVIDER_HARNESS[cred["provider"]]
    if cred["kind"] == "api_key":
        return RunAuth(harness=harness, env={harness.provider.env_var: cred["secret"]})

    # OAuth: the CLI reads a credential file, not an env var.
    if harness is harness_mod.CLAUDE:
        config_dir = f"{_SPRITE_HOME}/.claude"
        path = f"{config_dir}/.credentials.json"
        return RunAuth(
            harness=harness,
            env={"CLAUDE_CONFIG_DIR": config_dir},
            files={path: cred["secret"]},
            oauth_file=OAuthFile(cred["user_id"], cred["provider"], path),
        )
    # Codex ChatGPT sign-in → ~/.codex/auth.json.
    path = f"{_SPRITE_HOME}/.codex/auth.json"
    return RunAuth(
        harness=harness,
        env={},
        files={path: _codex_auth_json(cred["secret"])},
        oauth_file=OAuthFile(cred["user_id"], cred["provider"], path),
    )


def _oauth_tokens(provider: str, blob: dict) -> tuple[str | None, str | None, int]:
    """(access token, refresh token, expiry ms) from a stored secret or an
    on-box credential file. Codex carries no expiry, so its is always 0."""
    if provider == "anthropic":
        tokens = blob.get("claudeAiOauth") or {}
        return (
            tokens.get("accessToken"),
            tokens.get("refreshToken"),
            int(tokens.get("expiresAt") or 0),
        )
    # A stored Codex secret is either a full auth.json or the bare token set.
    tokens = blob.get("tokens") or blob
    return tokens.get("access_token"), tokens.get("refresh_token"), 0


async def save_refreshed(oauth_file: OAuthFile, contents: str) -> bool:
    """Store the credential file as the harness left it, if it refreshed the
    token during the turn. Returns whether anything was stored.

    The provider rotates the refresh token on every refresh, so the copy on
    the box is the only valid one afterwards. A file that is unparseable,
    missing a token, or older than what is stored (the user reconnected
    mid-turn) is ignored — a bad write here would break a working credential."""
    try:
        fresh = json.loads(contents)
    except ValueError:
        return False
    if not isinstance(fresh, dict):
        return False
    access, refresh, expires = _oauth_tokens(oauth_file.provider, fresh)
    if not access or not refresh:
        return False

    async with get_pool().acquire() as conn, conn.transaction():
        secret_enc = await conn.fetchval(
            "SELECT secret_enc FROM user_agent_credentials "
            "WHERE user_id = $1 AND provider = $2 AND kind = 'oauth' FOR UPDATE",
            oauth_file.user_id,
            oauth_file.provider,
        )
        if secret_enc is None:
            return False  # disconnected (or switched to an API key) mid-turn
        stored_access, stored_refresh, stored_expires = _oauth_tokens(
            oauth_file.provider, json.loads(_decrypt(secret_enc))
        )
        if (access, refresh) == (stored_access, stored_refresh) or expires < stored_expires:
            return False
        await conn.execute(
            "UPDATE user_agent_credentials SET secret_enc = $3 "
            "WHERE user_id = $1 AND provider = $2",
            oauth_file.user_id,
            oauth_file.provider,
            _encrypt(contents),
        )
    return True


_SPRITE_HOME = "/home/sprite"


def _codex_auth_json(secret: str) -> str:
    """A full auth.json (already has `tokens`) is written verbatim; a bare token
    set is wrapped into one, mirroring the Codex CLI's own file."""
    from datetime import UTC, datetime

    parsed = json.loads(secret)
    if "tokens" in parsed:
        return secret
    return json.dumps(
        {"OPENAI_API_KEY": None, "tokens": parsed, "last_refresh": datetime.now(UTC).isoformat()}
    )
