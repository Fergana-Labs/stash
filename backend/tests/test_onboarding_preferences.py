"""Web-onboarding preferences: stored by the web onboarding page, applied by
the next `stash signin`. The consumed_at stamp is the contract that stops a
later standalone signin from silently re-applying stale web choices, and a
fresh PUT must clear it so new web choices apply again.
"""

from pathlib import Path

from httpx import AsyncClient

from .conftest import unique_name

PREFS_URL = "/api/v1/me/onboarding-preferences"

VALID_PREFS = {
    "enabled_agents": ["claude", "codex"],
    "record_scope": "everything",
    "import_history": True,
    "claude_md_opt_in": False,
}


async def _register(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("onb"), "password": "securepassword1"},
    )
    return r.json()["api_key"]


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def test_no_preferences_reads_as_null(client: AsyncClient):
    """The CLI branches on this: null means "run the interactive wizard"."""
    key = await _register(client)
    r = await client.get(PREFS_URL, headers=_auth(key))
    assert r.status_code == 200
    assert r.json() == {"preferences": None}


async def test_put_stores_choices_unconsumed(client: AsyncClient):
    key = await _register(client)
    r = await client.put(PREFS_URL, json=VALID_PREFS, headers=_auth(key))
    assert r.status_code == 200

    stored = (await client.get(PREFS_URL, headers=_auth(key))).json()["preferences"]
    assert stored == {**VALID_PREFS, "consumed_at": None}


async def test_unknown_agent_is_rejected(client: AsyncClient):
    """The web must only offer agents the CLI can actually record."""
    key = await _register(client)
    r = await client.put(
        PREFS_URL,
        json={**VALID_PREFS, "enabled_agents": ["claude", "clippy"]},
        headers=_auth(key),
    )
    assert r.status_code == 400
    assert "clippy" in r.json()["detail"]


async def test_invalid_scope_is_rejected(client: AsyncClient):
    key = await _register(client)
    r = await client.put(
        PREFS_URL, json={**VALID_PREFS, "record_scope": "somewhere"}, headers=_auth(key)
    )
    assert r.status_code == 422


async def test_consume_stamps_consumed_at(client: AsyncClient):
    key = await _register(client)
    await client.put(PREFS_URL, json=VALID_PREFS, headers=_auth(key))

    r = await client.post(f"{PREFS_URL}/consume", headers=_auth(key))
    assert r.status_code == 200

    stored = (await client.get(PREFS_URL, headers=_auth(key))).json()["preferences"]
    assert stored["consumed_at"] is not None


async def test_consume_without_preferences_is_404(client: AsyncClient):
    key = await _register(client)
    r = await client.post(f"{PREFS_URL}/consume", headers=_auth(key))
    assert r.status_code == 404


async def test_new_put_resets_consumed_at(client: AsyncClient):
    """Re-running web onboarding supersedes an already-applied set: the next
    signin must apply the new choices, not skip them as consumed."""
    key = await _register(client)
    await client.put(PREFS_URL, json=VALID_PREFS, headers=_auth(key))
    await client.post(f"{PREFS_URL}/consume", headers=_auth(key))

    await client.put(PREFS_URL, json={**VALID_PREFS, "import_history": False}, headers=_auth(key))

    stored = (await client.get(PREFS_URL, headers=_auth(key))).json()["preferences"]
    assert stored["consumed_at"] is None
    assert stored["import_history"] is False


async def test_preferences_require_auth(client: AsyncClient):
    assert (await client.get(PREFS_URL)).status_code == 401
    assert (await client.put(PREFS_URL, json=VALID_PREFS)).status_code == 401
    assert (await client.post(f"{PREFS_URL}/consume")).status_code == 401


async def test_claude_md_block_serves_the_cli_file(client: AsyncClient):
    """The web preview must show byte-for-byte what `stash connect` appends —
    both sides read cli/claude_md_block.md."""
    r = await client.get("/api/v1/claude-md-block")
    assert r.status_code == 200
    block = r.json()["block"]
    cli_file = Path(__file__).resolve().parents[2] / "cli" / "claude_md_block.md"
    assert block == cli_file.read_text()
    assert block.startswith("<!-- stash-context -->")
