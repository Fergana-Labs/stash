"""Resolve which harness + credentials a user's cloud agent runs on.

The rule (mirrors Fleet's resolveUserKey, adapted to per-user sprites):

  1. Bring-your-own: the user connected Claude Code or Codex (API key or
     OAuth) → run THAT harness with THEIR credential. Backend holds nothing.
  2. Managed: no BYO credential but Pro → opencode on OpenRouter (GLM 5.2),
     billed to us. No Anthropic key involved.
  3. Neither: raise NeedsAuth — connect a key or upgrade.

Local exec mode: a connected local endpoint runs the machine's own pi (no
injection); none connected raises NeedsAuth; a connected endpoint under a
foreign pin keeps the machine's own harness login (no injection).

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
from urllib.parse import urlparse
from uuid import UUID

import httpx

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


# What a user typed into the base URL field, refused. The test-connection route
# answers with this same string so the form cannot learn two different messages
# for one mistake.
LOCAL_BASE_URL_HINT = (
    "base_url must be an absolute http(s) URL your cloud computer can reach "
    "(e.g. http://your-host:11434/v1)"
)

# The local endpoint probe: one GET of the endpoint's own model listing proves
# the server answers and, with a key attached, that the key is accepted. Both
# probes — the sprite's turn-time preflight and the Settings pre-save test —
# share this URL shape and this time budget.
LOCAL_PROBE_SUFFIX = "/models"
LOCAL_PROBE_TIMEOUT_S = 5.0


def local_probe_url(base_url: str) -> str:
    """The model listing for a base URL (http://host:11434/v1 → …/v1/models)."""
    return base_url.rstrip("/") + LOCAL_PROBE_SUFFIX


def local_endpoint_doc(base_url: str, model: str, api_key: str | None = None) -> dict:
    """The validated local endpoint form as a doc: the base URL the box dials,
    the model id on it, and an optional key.

    One validation surface for every place that takes these values — the
    personal connect, the workspace connect, and the pre-save test — so all of
    them refuse bad input with the same words.

    Raises ValueError with a user-facing detail on bad input; the endpoints map
    it to a 400.
    """
    base_url = base_url.strip()
    model = model.strip()
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(LOCAL_BASE_URL_HINT)
    if not model:
        raise ValueError("model is required for the local endpoint")
    return {
        "base_url": base_url,
        "model": model,
        "api_key": (api_key or "").strip() or None,  # keyless endpoints are common
    }


def local_endpoint_secret(base_url: str, model: str, api_key: str | None = None) -> str:
    """The stored doc for a local endpoint credential — an endpoint, not a bare
    key. Shared by the personal and the workspace connect endpoints so both
    validate and store one shape.
    """
    return json.dumps(local_endpoint_doc(base_url, model, api_key))


def _probe_models(body: str) -> list[str] | None:
    """The model ids of an OpenAI-shaped /models body, or None when the body is
    not that shape — a proxy's HTML landing page answers 200 and must not be
    reported as a working endpoint."""
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None
    return [m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]


def _probe_snippet(text: str, limit: int) -> str:
    """The provider's answer, whitespace-collapsed and capped, so a proxy's full
    HTML page never lands in the Settings form."""
    return " ".join(text.split())[:limit] or "(empty body)"


async def probe_local_endpoint(base_url: str, api_key: str | None) -> dict:
    """Dial the user's endpoint from the backend and report what it answered.

    The same request the sprite's turn-time preflight makes, with the candidate
    key attached — which is why it exists: the preflight can only prove reachability
    after a sprite exists, one turn too late. The endpoint's own words are returned
    because they are the only part that names the failure (LiteLLM says
    token_not_found_in_db where the HTTP layer says merely 401).

    Never reads or writes a stored credential: it tests exactly what it is given.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=LOCAL_PROBE_TIMEOUT_S, follow_redirects=False) as http:
            response = await http.get(local_probe_url(base_url), headers=headers)
    except httpx.TimeoutException:
        return {
            "ok": False,
            "http_status": None,
            "error_detail": f"timed out after {LOCAL_PROBE_TIMEOUT_S:g}s",
        }
    except httpx.HTTPError as e:
        return {
            "ok": False,
            "http_status": None,
            "error_detail": f"connection failed: {e}",
        }

    status = response.status_code
    body = response.text
    if 300 <= status < 400:
        return {
            "ok": False,
            "http_status": status,
            "error_detail": f"redirected to {response.headers.get('location', '?')} — a "
            "model endpoint must answer directly",
        }
    if 200 <= status < 300:
        models = _probe_models(body)
        if models is not None:
            return {"ok": True, "http_status": status, "models": models}
        return {
            "ok": False,
            "http_status": status,
            "error_detail": 'expected an OpenAI model list ({"data": [...]}), got: '
            + _probe_snippet(body, 400),
        }
    return {"ok": False, "http_status": status, "error_detail": _probe_snippet(body, 500)}


async def _get_credential(user_id: UUID, provider: str | None = None) -> dict | None:
    """The user's connected credential. With `provider`, only that one (so an
    agent's model override selects a specific connected harness)."""
    if provider is not None:
        row = await get_pool().fetchrow(
            "SELECT provider, kind, secret_enc, models_json_enc FROM user_agent_credentials "
            "WHERE user_id = $1 AND provider = $2",
            user_id,
            provider,
        )
    else:
        row = await get_pool().fetchrow(
            "SELECT provider, kind, secret_enc, models_json_enc FROM user_agent_credentials "
            "WHERE user_id = $1 ORDER BY created_at LIMIT 1",
            user_id,
        )
    if row is None:
        return None
    return {
        "provider": row["provider"],
        "kind": row["kind"],
        "secret": _decrypt(row["secret_enc"]),
        # NULL until the user stores their own pi models.json in Settings.
        "models_json": _decrypt(row["models_json_enc"]),
    }


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


async def local_credential(user_id: UUID) -> dict | None:
    """The user's stored local endpoint doc, or None when none is connected.

    The one credential the API hands back: the doc is the user's own endpoint
    config — base URL, model id, and the key to their own server — which the
    Settings form needs to show the key it holds and to prefill a reconnect.
    Another provider's secret never travels this path.
    """
    cred = await _get_credential(user_id, "local")
    if cred is None:
        return None
    if cred["kind"] != "endpoint":
        raise ValueError(f"local credential has unexpected kind: {cred['kind']}")
    return _local_credential_doc(cred)


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
    # Local mode: a connected local endpoint runs on the machine's own pi —
    # its credential is self-contained. With nothing connected, fail loud
    # (STAS-131) instead of riding the machine's unauthenticated login; a
    # connected local endpoint under a foreign pin keeps that machine login.
    if settings.AGENT_EXEC_MODE == "local":
        local_cred = await _get_credential(user_id, "local")
        if local_cred is None:
            # The old silent CLAUDE fallback crashed on boxes without the
            # binary and masked the missing credential row (STAS-131).
            raise NeedsAuth
        if prefer_provider in (None, "local"):
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


def _local_credential_doc(cred: dict) -> dict:
    doc = json.loads(cred["secret"])
    base_url = doc.get("base_url")
    model = doc.get("model")
    if not base_url or not model:
        raise ValueError("local credential is missing base_url or model")
    return doc


def _synthesized_models_json(base_url: str, model: str, key_ref: str) -> str:
    """The default pi provider config for a connected local endpoint — the
    single synthesis path, used by every turn and by the Settings reader when
    the user has not stored their own models.json."""
    return json.dumps(
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

    When the user stored their own models.json in Settings, its bytes are
    written VERBATIM (no parse, no re-serialize) — the stored text is the
    single source of truth. Endpoint, model, and the key env always come from
    the connect doc.
    """
    doc = _local_credential_doc(cred)
    base_url = doc["base_url"]
    model = doc["model"]
    env = {"PI_OFFLINE": "1", "HOME": home}  # no pi startup network calls
    api_key = doc.get("api_key")
    if api_key:
        env[model_provider.LOCAL.env_var] = api_key
        key_ref = "$STASH_LOCAL_KEY"
    else:
        key_ref = "local"
    override = cred.get("models_json")
    models_json = (
        override if override is not None else _synthesized_models_json(base_url, model, key_ref)
    )
    return RunAuth(
        harness=harness_mod.PI,
        env=env,
        files={f"{home}/.pi/agent/models.json": models_json},
        endpoint=base_url,
        model=model,
    )


async def get_local_models_json(user_id: UUID) -> dict:
    """The effective models.json for the user's local endpoint: the stored
    override when present, else the synthesized default for the connected
    endpoint. Returns {models_json: str, stored: bool}."""
    cred = await _get_credential(user_id, "local")
    if cred is None:
        raise LookupError("local endpoint is not connected")
    doc = _local_credential_doc(cred)
    key_ref = "$STASH_LOCAL_KEY" if doc.get("api_key") else "local"
    stored = cred.get("models_json")
    return {
        "models_json": (
            stored
            if stored is not None
            else _synthesized_models_json(doc["base_url"], doc["model"], key_ref)
        ),
        "stored": stored is not None,
    }


async def save_local_models_json(user_id: UUID, models_json: str) -> None:
    """Store the user's models.json VERBATIM (the raw text, never re-serialized).

    Validation is parse-don't-validate: the JSON must parse to an object with a
    top-level "providers" object, or the save fails loud. pi itself is the
    rest of the validator — no field patching or normalization here.
    """
    cred = await _get_credential(user_id, "local")
    if cred is None:
        raise LookupError("local endpoint is not connected")
    try:
        parsed = json.loads(models_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"models.json is not valid JSON: {e}") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("providers"), dict):
        raise ValueError('models.json must be a JSON object with a top-level "providers" object')
    await get_pool().execute(
        "UPDATE user_agent_credentials SET models_json_enc = $1 "
        "WHERE user_id = $2 AND provider = 'local'",
        _encrypt(models_json),
        user_id,
    )


async def reset_local_models_json(user_id: UUID) -> None:
    """Delete the stored override; the synthesized default returns."""
    cred = await _get_credential(user_id, "local")
    if cred is None:
        raise LookupError("local endpoint is not connected")
    await get_pool().execute(
        "UPDATE user_agent_credentials SET models_json_enc = NULL "
        "WHERE user_id = $1 AND provider = 'local'",
        user_id,
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
