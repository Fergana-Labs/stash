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
from . import billing_service, model_provider, sprite_service
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
    "local": harness_mod.PI,  # pi on the user's own OpenAI-compatible endpoint
}
# OpenRouter and local have no OAuth — API key only (local's key is optional).
_API_KEY_ONLY = {"openrouter", "local"}

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


@dataclass
class RunAuth:
    harness: harness_mod.Harness
    env: dict[str, str] = field(default_factory=dict)
    # Files to write on the box before the turn: {path: contents}. For OAuth.
    files: dict[str, str] = field(default_factory=dict)
    # Local model only: the OpenAI-compatible base URL the harness dials and
    # the model id within it (both set only for the LOCAL provider's PI run).
    endpoint: str | None = None
    model: str | None = None


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
    return {"provider": row["provider"], "kind": row["kind"], "secret": _decrypt(row["secret_enc"])}


async def store_credential(user_id: UUID, provider: str, kind: str, secret: str) -> None:
    if provider not in _PROVIDER_HARNESS:
        raise ValueError(f"unknown provider: {provider}")
    if kind not in ("api_key", "oauth", "endpoint"):
        raise ValueError(f"unknown credential kind: {kind}")
    if kind == "oauth" and provider in _API_KEY_ONLY:
        raise ValueError(f"{provider} does not support OAuth")
    # An endpoint credential is the local model's base URL + model doc — nothing
    # else has that shape.
    if kind == "endpoint" and provider != "local":
        raise ValueError(f"{provider} does not support endpoint credentials")
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

    In local exec mode a connected local endpoint still resolves to pi: its
    credential is self-contained (base URL + model), so no sprite is needed —
    and the turn runs against the simulated box's home, isolated from the
    developer's own pi config.
    """
    # Local dev: the machine's own harness login; inject nothing.
    if settings.AGENT_EXEC_MODE == "local":
        local_cred = await _get_credential(user_id, "local")
        if local_cred is not None and prefer_provider in (None, "local"):
            return _local_auth(local_cred, home=str(sprite_service.local_box_home()))
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
    if cred["provider"] == "local":
        return _local_auth(cred)
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


def _local_auth(cred: dict, home: str = _SPRITE_HOME) -> RunAuth:
    """Local model: the credential is a JSON doc describing the user's own
    OpenAI-compatible endpoint (base_url, model, optional api_key). pi reads a
    provider config file; the key, when set, rides only in the STASH_LOCAL_KEY
    env var that the file's $STASH_LOCAL_KEY interpolation expands.

    The key is never in argv, and a keyless endpoint gets a literal dummy so
    the file shape stays one codepath.

    `home` is the box's home dir: the real /home/sprite on a sprites box, or
    the simulated box home in local exec mode. pi resolves its config from
    $HOME, so the HOME override keeps a locally exec'd turn on the box config
    that carries this endpoint — never the developer's machine config.
    """
    doc = json.loads(cred["secret"])
    base_url = doc.get("base_url")
    model = doc.get("model")
    if not base_url or not model:
        raise ValueError("local credential is missing base_url or model")
    env = {"PI_OFFLINE": "1", "HOME": home}  # no pi startup network calls
    api_key = doc.get("api_key")
    if api_key:
        env[model_provider.LOCAL.env_var] = api_key
        key_ref = "$STASH_LOCAL_KEY"
    else:
        key_ref = "local"
    models_json = json.dumps(
        {
            "providers": {
                "local": {
                    "baseUrl": base_url,
                    "api": "openai-completions",
                    "apiKey": key_ref,
                    # Ollama-style servers reject OpenAI's developer role and
                    # reasoning_effort; these flags keep pi off both.
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [{"id": model, "contextWindow": 131072, "maxTokens": 8192}],
                }
            }
        },
        indent=2,
    )
    return RunAuth(
        harness=harness_mod.PI,
        env=env,
        files={f"{home}/.pi/agent/models.json": models_json},
        endpoint=base_url,
        model=model,
    )


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
