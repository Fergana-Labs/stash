from uuid import UUID

import httpx
import pytest

from backend.integrations.heavi import client, indexer
from backend.integrations.heavi.provider import HeaviIntegration


def _async(value):
    async def result(*args, **kwargs):
        return value

    return result


def _rule(rule_id="learning_1_abc", summary="Prefer OEM brake calipers", **overrides):
    rule = {
        "id": rule_id,
        "summary": summary,
        "source_type": "manual",
        "created_at": "2026-06-10T00:00:00Z",
        "updated_at": "2026-06-10T00:00:00Z",
    }
    rule.update(overrides)
    return rule


# --- rendering ---------------------------------------------------------------


def test_rule_paths_keep_duplicate_summaries_distinct_and_strip_slashes():
    first = indexer.rule_path(_rule("learning_1_a", "Avoid generic DEF sensors / always OEM"))
    second = indexer.rule_path(_rule("learning_2_b", "Avoid generic DEF sensors / always OEM"))
    assert first == "Avoid generic DEF sensors - always OEM (learning_1_a)"
    assert first != second


def test_rule_content_names_the_rejected_candidate_for_feedback_rules():
    feedback = indexer.rule_content(_rule(source_type="user_feedback", source_id="cand_9d3k1"))
    assert "user_feedback (candidate cand_9d3k1)" in feedback
    manual = indexer.rule_content(_rule(source_type="manual"))
    assert "source: manual" in manual


def test_rule_entries_sort_newest_first_and_honor_prefix():
    rules = [
        _rule("learning_1_a", "Old rule", created_at="2026-01-01T00:00:00Z"),
        _rule("learning_2_b", "New rule", created_at="2026-07-01T00:00:00Z"),
    ]
    entries = indexer.rule_entries(rules)
    assert [e["name"] for e in entries] == ["New rule", "Old rule"]
    assert all(e["kind"] == "rule" for e in entries)
    assert indexer.rule_entries(rules, prefix="New") == [entries[0]]


def test_find_rule_matches_full_path_or_raw_id():
    rules = [_rule("learning_1_a", "Prefer OEM")]
    assert indexer.find_rule(rules, "Prefer OEM (learning_1_a)") == rules[0]
    assert indexer.find_rule(rules, "learning_1_a") == rules[0]
    assert indexer.find_rule(rules, "nonsense") is None


# --- indexer -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_heavi_upserts_every_rule_and_tombstones_the_rest(monkeypatch):
    rules = [
        _rule("learning_1_a", "Prefer OEM"),
        _rule(
            "learning_2_b", "Avoid generic sensors", source_type="user_feedback", source_id="cand_1"
        ),
    ]
    upserts: list[dict] = []
    removed: list = []

    async def capture_upsert(**kwargs):
        upserts.append(kwargs)
        return "inserted"

    async def capture_remove(table, source_id, present):
        removed.append((table, source_id, present))

    monkeypatch.setattr(indexer, "fetch_learnings", _async(rules))
    monkeypatch.setattr(indexer.source_service, "upsert_content_document", capture_upsert)
    monkeypatch.setattr(indexer.source_service, "remove_missing_documents", capture_remove)

    cursor = await indexer.index_heavi({"id": str(UUID(int=1)), "owner_user_id": str(UUID(int=2))})

    assert cursor is None
    assert [u["external_ref"] for u in upserts] == ["learning_1_a", "learning_2_b"]
    assert all(u["table"] == "heavi_learning_docs" for u in upserts)
    assert all(u["kind"] == "rule" for u in upserts)
    (table, source_id, present) = removed[0]
    assert table == "heavi_learning_docs"
    assert source_id == UUID(int=1)
    assert present == [u["path"] for u in upserts]


# --- client ------------------------------------------------------------------


def _fake_get(payload):
    async def fake_get(self, url):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    return fake_get


@pytest.mark.asyncio
async def test_fetch_learnings_returns_valid_rows(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get([_rule()]))
    rows = await client.fetch_learnings_with("https://example.com/api/learnings", "token")
    assert rows == [_rule()]


@pytest.mark.asyncio
async def test_fetch_learnings_rejects_non_array_payloads(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get({"learnings": []}))
    with pytest.raises(ValueError, match="JSON array"):
        await client.fetch_learnings_with("https://example.com/api/learnings", "token")


@pytest.mark.asyncio
async def test_fetch_learnings_rejects_rows_missing_required_fields(monkeypatch):
    incomplete = {"id": "learning_1_a", "summary": "Prefer OEM"}
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get([incomplete]))
    with pytest.raises(ValueError, match="required fields"):
        await client.fetch_learnings_with("https://example.com/api/learnings", "token")


# --- provider ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_validates_endpoint_and_bundles_credentials(monkeypatch):
    import backend.integrations.heavi.provider as provider_module

    monkeypatch.setattr(
        provider_module, "fetch_learnings_with", _async([_rule(), _rule("learning_2_b")])
    )
    token, account = await HeaviIntegration().connect_with_credentials(
        {"base_url": "https://example.com/api/learnings/", "api_token": "tok"}
    )
    import json

    bundle = json.loads(token.access_token)
    assert bundle == {"base_url": "https://example.com/api/learnings", "api_token": "tok"}
    assert token.expires_at is None
    assert account.display_name == "Rules of the Road (2 rules)"


@pytest.mark.asyncio
async def test_connect_rejects_non_https_and_missing_token():
    with pytest.raises(ValueError, match="https"):
        await HeaviIntegration().connect_with_credentials(
            {"base_url": "http://example.com", "api_token": "tok"}
        )
    with pytest.raises(ValueError, match="api_token"):
        await HeaviIntegration().connect_with_credentials(
            {"base_url": "https://example.com", "api_token": ""}
        )


# --- end to end: connect -> add source -> live ls/cat -------------------------

BASE_URL = "https://example.com/api/learnings"


def _stub_heavi_endpoint(monkeypatch, rules: list[dict]):
    """Serve `rules` (live — mutations show up) for GETs to BASE_URL; every
    other URL passes through so the ASGI test client keeps working."""
    real_get = httpx.AsyncClient.get

    async def fake_get(self, url, **kwargs):
        if str(url) == BASE_URL:
            return httpx.Response(200, json=rules, request=httpx.Request("GET", url))
        return await real_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


async def _register_user(client, pool=None, email: str | None = None) -> dict:
    """Register a user; with `email`, stamp it verified (the gate's trust
    anchor — registration itself has no email step)."""
    from .conftest import unique_name

    register = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("heavi"), "password": "securepassword1"},
    )
    assert register.status_code == 201
    body = register.json()
    if email is not None:
        await pool.execute(
            "UPDATE users SET email = $1, email_verified = TRUE WHERE id = $2",
            email,
            UUID(body["id"]),
        )
    return body


@pytest.mark.asyncio
async def test_provider_hidden_and_connect_rejected_for_non_heavi_users(client, pool, monkeypatch):
    from cryptography.fernet import Fernet

    from backend.config import settings

    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    body = await _register_user(client)  # no email at all
    headers = {"Authorization": f"Bearer {body['api_key']}"}

    listing = await client.get("/api/v1/integrations", headers=headers)
    assert "heavi" not in [p["provider"] for p in listing.json()["providers"]]

    rejected = await client.post(
        "/api/v1/integrations/heavi/credentials",
        json={"base_url": BASE_URL, "api_token": "tok"},
        headers=headers,
    )
    assert rejected.status_code == 403

    # A verified email on the wrong domain is still rejected.
    outsider = await _register_user(client, pool, email="alice@example.com")
    outsider_headers = {"Authorization": f"Bearer {outsider['api_key']}"}
    listing = await client.get("/api/v1/integrations", headers=outsider_headers)
    assert "heavi" not in [p["provider"] for p in listing.json()["providers"]]


@pytest.mark.asyncio
async def test_provider_visible_for_heavi_domain_and_workspace_scope(client, pool):
    body = await _register_user(client, pool, email="mike@heaviai.com")
    headers = {"Authorization": f"Bearer {body['api_key']}"}
    listing = await client.get("/api/v1/integrations", headers=headers)
    assert "heavi" in [p["provider"] for p in listing.json()["providers"]]

    # An unverified email on the right domain does NOT qualify.
    await pool.execute("UPDATE users SET email_verified = FALSE WHERE id = $1", UUID(body["id"]))
    listing = await client.get("/api/v1/integrations", headers=headers)
    assert "heavi" not in [p["provider"] for p in listing.json()["providers"]]

    # The Heavi workspace's scope user qualifies through workspaces.domain.
    from backend.auth import create_api_key
    from backend.services import workspace_service

    workspace = await workspace_service.create_workspace("Heavi", "heaviai.com")
    scope_key = await create_api_key(
        workspace["scope_user_id"], name="test", key_type="machine", access="full"
    )
    scope_headers = {"Authorization": f"Bearer {scope_key}"}
    listing = await client.get("/api/v1/integrations", headers=scope_headers)
    assert "heavi" in [p["provider"] for p in listing.json()["providers"]]


@pytest.mark.asyncio
async def test_connect_add_source_then_ls_and_cat_read_live(client, pool, monkeypatch):
    from cryptography.fernet import Fernet

    from backend.config import settings

    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    rules = [_rule("learning_1_a", "Prefer OEM brake calipers")]
    _stub_heavi_endpoint(monkeypatch, rules)

    body = await _register_user(client, pool, email="mike@heaviai.com")
    headers = {"Authorization": f"Bearer {body['api_key']}"}

    connected = await client.post(
        "/api/v1/integrations/heavi/credentials",
        json={"base_url": BASE_URL, "api_token": "tok"},
        headers=headers,
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["account_display_name"] == "Rules of the Road (1 rule)"

    created = await client.post(
        "/api/v1/me/sources",
        json={"source_type": "heavi_learnings"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    source = created.json()
    assert source["external_ref"] == BASE_URL
    assert source["display_name"] == "Heavi — Rules of the Road"

    # Nothing has synced into the cache table — a live listing is the only way
    # this can return anything.
    entries = await client.get(f"/api/v1/me/sources/{source['id']}/entries", headers=headers)
    assert entries.status_code == 200, entries.text
    assert [e["name"] for e in entries.json()["entries"]] == ["Prefer OEM brake calipers"]

    path = entries.json()["entries"][0]["path"]
    doc = await client.get(
        f"/api/v1/me/sources/{source['id']}/doc", params={"ref": path}, headers=headers
    )
    assert doc.status_code == 200, doc.text
    assert "Prefer OEM brake calipers" in doc.json()["content"]
    assert "source: manual" in doc.json()["content"]

    # A rule added upstream appears on the very next ls — no sync in between.
    rules.append(_rule("learning_2_b", "Never use generic DEF sensors"))
    entries = await client.get(f"/api/v1/me/sources/{source['id']}/entries", headers=headers)
    names = [e["name"] for e in entries.json()["entries"]]
    assert "Never use generic DEF sensors" in names
