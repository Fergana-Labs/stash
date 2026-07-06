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
     ~/.codex/auth.json). The OAuth acquisition flow is a separate follow-up;
     this module already injects a stored OAuth token if one exists.
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
    "anthropic": harness_mod.CLAUDE,   # Claude Code
    "openai": harness_mod.CODEX,       # Codex
    "openrouter": harness_mod.OPENCODE,  # opencode on the user's OpenRouter key
}
# OpenRouter has no OAuth — API key only.
_API_KEY_ONLY = {"openrouter"}

# The managed agent: opencode driving OpenRouter's GLM 5.2, on our key.
MANAGED_HARNESS = harness_mod.OPENCODE


@dataclass
class RunAuth:
    harness: harness_mod.Harness
    env: dict[str, str] = field(default_factory=dict)
    # Files to write on the box before the turn: {path: contents}. For OAuth.
    files: dict[str, str] = field(default_factory=dict)


async def _get_credential(user_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        "SELECT provider, kind, secret_enc FROM user_agent_credentials "
        "WHERE user_id = $1 ORDER BY created_at LIMIT 1",
        user_id,
    )
    if row is None:
        return None
    return {"provider": row["provider"], "kind": row["kind"],
            "secret": _decrypt(row["secret_enc"])}


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


async def resolve(user_id: UUID) -> RunAuth:
    """The harness + credential injection for this user's next turn."""
    # Local dev: the machine's own harness login; inject nothing.
    if settings.AGENT_EXEC_MODE == "local":
        return RunAuth(harness=harness_mod.CLAUDE)

    cred = await _get_credential(user_id)
    if cred is not None:
        return _byo_auth(cred)

    # No connected credential → managed agent, Pro only.
    if not await billing_service.is_pro(user_id):
        raise NeedsAuth
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise ProviderNotConfigured
    return RunAuth(harness=MANAGED_HARNESS, env={model_provider.OPENROUTER.env_var: key})


def _byo_auth(cred: dict) -> RunAuth:
    harness = _PROVIDER_HARNESS[cred["provider"]]
    if cred["kind"] == "api_key":
        return RunAuth(harness=harness, env={harness.provider.env_var: cred["secret"]})

    # OAuth: the CLI reads a credential file, not an env var.
    if harness is harness_mod.CLAUDE:
        config_dir = f"{_SPRITE_HOME}/.claude"
        return RunAuth(
            harness=harness,
            env={"CLAUDE_CONFIG_DIR": config_dir},
            files={f"{config_dir}/.credentials.json": cred["secret"]},
        )
    # Codex ChatGPT sign-in → ~/.codex/auth.json.
    return RunAuth(
        harness=harness,
        env={},
        files={f"{_SPRITE_HOME}/.codex/auth.json": _codex_auth_json(cred["secret"])},
    )


_SPRITE_HOME = "/home/sprite"


def _codex_auth_json(secret: str) -> str:
    # A full auth.json is stored verbatim; a bare token is wrapped.
    stripped = secret.strip()
    if stripped.startswith("{"):
        return stripped
    return json.dumps({"OPENAI_API_KEY": None, "tokens": json.loads(stripped)})
