"""Trained models: the corpus gate, the one-time purchase, and the model's
life from queued to ready or failed.

Why these matter: money and GPU time are spent here. A purchase must be
recorded exactly once per Stripe session however many times the webhook
fires, consumed exactly once per training run, and handed back when the run
fails. A corpus that would waste a run never reaches the GPU. And nothing
here is visible across accounts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient

from backend.config import settings
from backend.services import files_tree_service
from backend.trained_models import gpu, purchases, service, tasks
from backend.trained_models.kinds import stylewriter
from backend.trained_models.kinds.stylewriter import corpus

from .conftest import unique_name

PROSE = (
    "I keep coming back to the same idea. Memory is not a feature you bolt onto an "
    "agent; it is a control problem. Every time we tried the easy version it worked "
    "for a week and then quietly drifted, and nobody could say when it had started. "
)  # 47 words


def prose(words: int) -> str:
    """Distinct paragraphs, because identical passages are deduplicated."""
    out = []
    while sum(len(p.split()) for p in out) < words:
        out.append(f"{PROSE}That was attempt number {len(out) + 1}, and it taught us something.")
    return "\n\n".join(out)


async def _register(client: AsyncClient, prefix: str = "tm") -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _corpus_folder(user_id: UUID, words: int, name: str = "Writing samples") -> UUID:
    folder = await files_tree_service.create_folder(user_id, name, user_id)
    await files_tree_service.create_page(
        user_id, "essay.md", user_id, folder_id=folder["id"], content=prose(words)
    )
    return folder["id"]


def _stripe_signature(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_x")
    monkeypatch.setattr(settings, "STRIPE_STYLEWRITER_PRICE_ID", "price_test_train")
    monkeypatch.setattr(settings, "INTERNAL_DOMAINS_FREE_PRO", False)


@pytest.fixture(autouse=True)
def no_default(monkeypatch, tmp_path):
    """The repo ships a default profile; these tests reason about a user's
    own models, so the shared one is absent unless a test asks for it."""
    monkeypatch.setattr(stylewriter, "DEFAULT_PROFILE_PATH", tmp_path / "no-default.json")


@pytest.fixture
def gpu_stubbed(monkeypatch):
    """No GPU in tests: training starts instantly and the poll task is a no-op."""
    monkeypatch.setattr(settings, "STYLEWRITER_GPU_URL", "https://gpu.example/api")

    async def start(url, op, payload):
        assert op == "train_start"
        assert payload["chunks"], "training must send the passages"
        return "fc-test-job"

    monkeypatch.setattr(gpu, "start", start)
    monkeypatch.setattr(tasks.poll_training, "delay", lambda model_id: None)


# ── The corpus cleaner (pure) ─────────────────────────────────────────


def test_cleaner_keeps_only_prose():
    text = (
        "# A heading\n\n"
        "Real prose that someone wrote, long enough to count as a paragraph of writing "
        "with more than twenty five words in it so it is kept as a passage.\n\n"
        "- a bullet\n- another bullet\n\n"
        "> a quote from someone else\n\n"
        "```\ncode = 1\n```\n\n"
        "| a | table |\n|---|---|\n\n"
        "See [the docs](https://example.com) and https://example.com for **more**."
    )
    paragraphs = corpus.paragraphs(text)
    assert paragraphs[0].startswith("Real prose that someone wrote")
    assert paragraphs[-1] == "See the docs and for more."
    # An export's sign-off would teach the model to sign off and stop.
    assert corpus.paragraphs("Real words here.\n\n— @samzliu · 2026-01-30\nhttps://x.com/i/1") == [
        "Real words here."
    ]
    # A bare title line and a trailing references label are structure too.
    assert corpus.paragraphs(
        "I quit my PhD at Stanford\n\nWhen I left, my dad was not pleased."
    ) == ["When I left, my dad was not pleased."]
    assert corpus.paragraphs("A sentence first.\n\nMore here.\n\nReferences\n") == [
        "A sentence first.",
        "More here.",
    ]
    assert not any("bullet" in p or "quote" in p or "code" in p or "table" in p for p in paragraphs)


def test_corpus_gates_and_dedupes():
    blocked = corpus.inspect([corpus.Document("a.md", prose(600))])
    assert blocked.status == "blocked" and not blocked.ready
    assert "1,000" in blocked.reasons[0]

    warned = corpus.inspect([corpus.Document("a.md", prose(1_200))])
    assert warned.status == "warning" and warned.ready
    assert "2,000" in warned.warnings[0]

    duplicated = corpus.inspect(
        [corpus.Document("a.md", prose(2_100)), corpus.Document("copy.md", prose(2_100))]
    )
    assert duplicated.duplicate_chunks > 0
    assert (
        duplicated.usable_words
        == corpus.inspect([corpus.Document("a.md", prose(2_100))]).usable_words
    )

    empty = corpus.inspect([])
    assert empty.status == "blocked"
    assert corpus.inspect([corpus.Document("x.md", "# only a heading")]).usable_documents == 0


def test_report_dict_never_carries_the_passages():
    report = corpus.inspect([corpus.Document("a.md", prose(2_100))])
    data = report.to_dict()
    assert isinstance(data["chunks"], int)
    assert data["minimum_words"] == 1000 and data["ready"] is True


# ── Corpus check over real folders ────────────────────────────────────


async def test_check_corpus_reads_the_folder_pages(client, pool):
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    resp = await client.post(
        "/api/v1/me/models/check-corpus",
        json={"kind": "stylewriter", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready" and body["usable_words"] >= 2_000
    assert body["folder"]["name"] == "Writing samples"


async def test_check_corpus_unknown_folder_and_kind(client):
    key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/models/check-corpus",
        json={"kind": "stylewriter", "folder": "Nope"},
        headers=_auth(key),
    )
    assert resp.status_code == 404
    resp = await client.post(
        "/api/v1/me/models/check-corpus",
        json={"kind": "voiceclone", "folder": "Nope"},
        headers=_auth(key),
    )
    assert resp.status_code == 404
    assert "unknown model kind" in resp.json()["detail"]


# ── Paying for a run ──────────────────────────────────────────────────


async def test_train_requires_payment_when_billing_is_on(
    client, billing_on, gpu_stubbed, monkeypatch
):
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)

    async def checkout(user, owner_user_id, kind, price_id):
        assert kind == "stylewriter" and price_id == "price_test_train"
        return "https://checkout.stripe.test/s"

    monkeypatch.setattr(service.billing_service, "create_purchase_checkout", checkout)
    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "me", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["checkout_url"] == "https://checkout.stripe.test/s"
    assert await service.list_models(user_id) == []


async def test_webhook_records_a_purchase_exactly_once(client, pool, billing_on):
    _, user_id = await _register(client)
    payload = json.dumps(
        {
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_train_1",
                    "mode": "payment",
                    "customer": "cus_none",
                    "amount_total": 2000,
                    "metadata": {
                        "purchase": "training",
                        "kind": "stylewriter",
                        "owner_user_id": str(user_id),
                    },
                }
            },
        }
    ).encode()
    for _ in range(2):
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": _stripe_signature(payload, "whsec_test_x")},
        )
        assert resp.status_code == 200
    assert await purchases.spendable_count(user_id, "stylewriter") == 1
    assert (
        await pool.fetchval("SELECT count(*) FROM user_subscriptions WHERE user_id = $1", user_id)
        == 0
    )

    # Someone else's one-time checkout on the same Stripe account is ignored.
    foreign = json.dumps(
        {
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_other", "mode": "payment", "amount_total": 500}},
        }
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhook",
        content=foreign,
        headers={"stripe-signature": _stripe_signature(foreign, "whsec_test_x")},
    )
    assert resp.status_code == 200
    assert await purchases.spendable_count(user_id, "stylewriter") == 1


async def test_train_consumes_the_purchase_and_starts_the_job(
    client, pool, billing_on, gpu_stubbed, monkeypatch
):
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    await purchases.record(user_id, "stylewriter", "cs_paid", 2000)

    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "me", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "training" and body["words"] >= 2_000
    assert "provider_ref" not in body and "profile" not in body
    assert await purchases.spendable_count(user_id, "stylewriter") == 0
    row = await pool.fetchrow(
        "SELECT job_ref, purchase_id FROM trained_models WHERE id = $1", UUID(body["id"])
    )
    assert row["job_ref"] == "fc-test-job" and row["purchase_id"] is not None

    # A second run needs a second purchase.
    async def checkout(user, owner_user_id, kind, price_id):
        return "https://checkout.stripe.test/again"

    monkeypatch.setattr(service.billing_service, "create_purchase_checkout", checkout)
    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "work", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 402


async def test_failed_start_hands_the_purchase_back(client, billing_on, gpu_stubbed, monkeypatch):
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    await purchases.record(user_id, "stylewriter", "cs_paid2", 2000)

    async def broken(url, op, payload):
        raise RuntimeError("gpu down")

    monkeypatch.setattr(gpu, "start", broken)
    with pytest.raises(RuntimeError):
        await service.train(
            user_id,
            {"id": user_id, "email": "x@example.com"},
            "stylewriter",
            "me",
            "Writing samples",
        )
    assert await purchases.spendable_count(user_id, "stylewriter") == 1
    assert await service.list_models(user_id) == []


async def test_billing_off_trains_for_free(client, gpu_stubbed, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "me", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text


async def test_blocked_corpus_never_reaches_the_gpu(client, gpu_stubbed, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 400)

    async def never(url, op, payload):
        raise AssertionError("must not start a job on a blocked corpus")

    monkeypatch.setattr(gpu, "start", never)
    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "me", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["status"] == "blocked"


async def test_bad_and_taken_names(client, gpu_stubbed, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    body = {"kind": "stylewriter", "name": "Me Too", "folder": "Writing samples"}
    assert (
        await client.post("/api/v1/me/models", json=body, headers=_auth(key))
    ).status_code == 422
    body["name"] = "me"
    assert (
        await client.post("/api/v1/me/models", json=body, headers=_auth(key))
    ).status_code == 201
    assert (
        await client.post("/api/v1/me/models", json=body, headers=_auth(key))
    ).status_code == 409


# ── From training to ready or failed ──────────────────────────────────


async def _queued_model(client, monkeypatch) -> tuple[str, UUID, UUID]:
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    model = await service.train(
        user_id, {"id": user_id, "email": "x@example.com"}, "stylewriter", "me", "Writing samples"
    )
    return key, user_id, model["id"]


async def test_training_result_makes_the_model_ready(client, pool, gpu_stubbed, monkeypatch):
    key, user_id, model_id = await _queued_model(client, monkeypatch)

    async def done(url, call_id):
        assert call_id == "fc-test-job"
        return {
            "adapter_path": "/adapters/model_x",
            "profile": {"mean": [1.0], "std": [1.0]},
            "pairs": 40,
        }

    monkeypatch.setattr(gpu, "result", done)
    assert await service.advance_training(model_id) == "ready"
    model = await service.get_model(user_id, "stylewriter", "me")
    assert model["status"] == "ready" and model["provider_ref"] == "/adapters/model_x"
    assert model["profile"] == {"mean": [1.0], "std": [1.0]} and model["trained_at"] is not None
    assert "provider_ref" not in service.public(model)
    # Polling a finished run changes nothing.
    assert await service.advance_training(model_id) == "ready"


async def test_failed_training_restores_the_purchase(
    client, pool, billing_on, gpu_stubbed, monkeypatch
):
    key, user_id = await _register(client)
    await _corpus_folder(user_id, 2_200)
    await purchases.record(user_id, "stylewriter", "cs_paid3", 2000)
    model = await service.train(
        user_id, {"id": user_id, "email": "x@example.com"}, "stylewriter", "me", "Writing samples"
    )
    assert await purchases.spendable_count(user_id, "stylewriter") == 0

    async def failed(url, call_id):
        raise gpu.GpuJobFailed("CUDA out of memory")

    monkeypatch.setattr(gpu, "result", failed)
    assert await service.advance_training(model["id"]) == "failed"
    assert await purchases.spendable_count(user_id, "stylewriter") == 1
    assert "CUDA" in (await service.get_model(user_id, "stylewriter", "me"))["error"]


async def test_still_running_keeps_training(client, gpu_stubbed, monkeypatch):
    _, user_id, model_id = await _queued_model(client, monkeypatch)

    async def pending(url, call_id):
        return None

    monkeypatch.setattr(gpu, "result", pending)
    assert await service.advance_training(model_id) == "training"


# ── Using a model ─────────────────────────────────────────────────────


async def test_run_rejects_unready_models_and_unknown_ops(client, gpu_stubbed, monkeypatch):
    key, user_id, model_id = await _queued_model(client, monkeypatch)
    resp = await client.post(
        "/api/v1/me/models/stylewriter/me/run",
        json={"op": "write", "input": {"notes": ["a"]}},
        headers=_auth(key),
    )
    assert resp.status_code == 409
    resp = await client.post(
        "/api/v1/me/models/stylewriter/me/run",
        json={"op": "compose", "input": {}},
        headers=_auth(key),
    )
    assert resp.status_code == 422
    assert "unknown operation" in resp.json()["detail"]


async def test_run_validates_input_and_sends_the_adapter(client, pool, gpu_stubbed, monkeypatch):
    key, user_id, model_id = await _queued_model(client, monkeypatch)
    await service.mark_ready(
        model_id, {"adapter_path": "/adapters/model_x", "profile": {"mean": [], "std": []}}
    )

    sent = {}

    async def start(url, op, payload):
        sent.update(payload)
        return "fc-gen"

    async def wait(url, call_id, seconds, every=2.0):
        return {
            "text": "In my voice.",
            "style_score": 0.6,
            "p_human": 0.9,
            "draws": 4,
            "soft_failed": False,
        }

    monkeypatch.setattr(gpu, "start", start)
    monkeypatch.setattr(gpu, "wait", wait)
    resp = await client.post(
        "/api/v1/me/models/stylewriter/me/run",
        json={"op": "write", "input": {"notes": ["the wedge is trust"], "length": "short"}},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done" and resp.json()["text"] == "In my voice."
    assert sent["adapter_path"] == "/adapters/model_x" and sent["operation"] == "write"
    assert sent["notes"] == ["the wedge is trust"] and sent["length"] == "short"

    with pytest.raises(ValueError):
        await service.run(user_id, "stylewriter", "me", "write", {"notes": []})


async def test_pending_generation_returns_a_job_id(client, gpu_stubbed, monkeypatch):
    key, user_id, model_id = await _queued_model(client, monkeypatch)
    await service.mark_ready(
        model_id, {"adapter_path": "/adapters/model_x", "profile": {"mean": [], "std": []}}
    )

    async def start(url, op, payload):
        return "fc-cold"

    async def wait(url, call_id, seconds, every=2.0):
        return None

    async def result(url, call_id):
        return {
            "text": "Later.",
            "style_score": 0.5,
            "p_human": 0.8,
            "draws": 4,
            "soft_failed": False,
        }

    monkeypatch.setattr(gpu, "start", start)
    monkeypatch.setattr(gpu, "wait", wait)
    monkeypatch.setattr(gpu, "result", result)
    first = await service.run(user_id, "stylewriter", "me", "rewrite", {"text": "Hello there."})
    assert first["status"] == "pending" and first["job_id"] == "fc-cold"
    later = await service.job_result(user_id, "stylewriter", "me", "fc-cold")
    assert later["status"] == "done" and later["text"] == "Later."


# ── Scope ─────────────────────────────────────────────────────────────


async def test_models_are_private_to_their_owner(client, gpu_stubbed, monkeypatch):
    key, user_id, _ = await _queued_model(client, monkeypatch)
    other_key, _ = await _register(client, "other")
    assert (await client.get("/api/v1/me/models", headers=_auth(key))).json()[0]["name"] == "me"
    assert (await client.get("/api/v1/me/models", headers=_auth(other_key))).json() == []
    resp = await client.get("/api/v1/me/models/stylewriter/me", headers=_auth(other_key))
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/me/models/stylewriter/me", headers=_auth(other_key))
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/me/models/stylewriter/me", headers=_auth(key))
    assert resp.status_code == 204


async def test_setup_status_tells_the_agent_what_is_next(client, billing_on, gpu_stubbed):
    key, user_id = await _register(client)
    resp = await client.get("/api/v1/me/models/setup-status/stylewriter", headers=_auth(key))
    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == [] and body["paid_runs_available"] == 0
    assert "checkout" in body["next_step"] and "$20" in body["training_fee"]
    assert stylewriter.TITLE == body["title"]


# ── The MCP server ────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def mcp_running():
    """The test client never runs the app lifespan, and the streamable-HTTP
    session manager can only be started once per process."""
    from backend.trained_models import mcp as trained_models_mcp

    async with trained_models_mcp.lifespan():
        yield


async def _mcp(client, key: str | None, method: str, params: dict | None = None):
    headers = {"Accept": "application/json, text/event-stream"}
    if key:
        headers.update(_auth(key))
    return await client.post(
        "/mcp/stylewriter",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=headers,
    )


async def test_mcp_requires_a_full_access_key(client, mcp_running):
    resp = await _mcp(client, None, "tools/list")
    assert resp.status_code == 401
    resp = await _mcp(client, "mc_bogus", "tools/list")
    assert resp.status_code == 401


async def test_mcp_lists_the_skills_tools(client, mcp_running):
    key, _ = await _register(client)
    resp = await _mcp(client, key, "tools/list")
    assert resp.status_code == 200, resp.text
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert {
        "setup_status",
        "check_corpus",
        "train",
        "job_result",
        "write",
        "continue",
        "edit_span",
        "score",
    } <= names


async def test_mcp_tools_run_as_the_caller(client, billing_on, mcp_running):
    key, user_id = await _register(client)
    resp = await _mcp(client, key, "tools/call", {"name": "setup_status", "arguments": {}})
    assert resp.status_code == 200, resp.text
    payload = json.loads(resp.json()["result"]["content"][0]["text"])
    assert payload["models"] == [] and payload["kind"] == "stylewriter"


# ── The shared default model ──────────────────────────────────────────


@pytest.fixture
def default_shipped(no_default, monkeypatch, tmp_path):
    """A shipped default: its presence is the profile file."""
    path = tmp_path / "default_profile.json"
    path.write_text(
        json.dumps(
            {
                "profile": {"mean": [1.0], "std": [1.0]},
                "corpus": {"usable_words": 14_000, "chunks": 40, "sources": ["a.md"]},
            }
        )
    )
    monkeypatch.setattr(stylewriter, "DEFAULT_PROFILE_PATH", path)


async def test_default_model_is_listed_runnable_and_kept(
    client, gpu_stubbed, default_shipped, monkeypatch
):
    key, user_id = await _register(client)
    listed = (await client.get("/api/v1/me/models", headers=_auth(key))).json()
    assert [(m["name"], m["shared"], m["status"]) for m in listed] == [("default", True, "ready")]

    sent = {}

    async def start(url, op, payload):
        sent.update(payload)
        return "fc-gen"

    async def wait(url, call_id, seconds, every=2.0):
        return {
            "text": "House voice.",
            "style_score": 0.5,
            "p_human": 0.9,
            "draws": 4,
            "soft_failed": False,
        }

    monkeypatch.setattr(gpu, "start", start)
    monkeypatch.setattr(gpu, "wait", wait)
    resp = await client.post(
        "/api/v1/me/models/stylewriter/default/run",
        json={"op": "write", "input": {"notes": ["a fact"]}},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert sent["adapter_path"] == stylewriter.DEFAULT_ADAPTER

    assert (
        await client.delete("/api/v1/me/models/stylewriter/default", headers=_auth(key))
    ).status_code == 409
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    await _corpus_folder(user_id, 2_200)
    resp = await client.post(
        "/api/v1/me/models",
        json={"kind": "stylewriter", "name": "default", "folder": "Writing samples"},
        headers=_auth(key),
    )
    assert resp.status_code == 422

    status = (
        await client.get("/api/v1/me/models/setup-status/stylewriter", headers=_auth(key))
    ).json()
    assert "shared default" in status["next_step"]


async def test_no_default_until_one_is_shipped(client, monkeypatch, tmp_path):
    monkeypatch.setattr(stylewriter, "DEFAULT_PROFILE_PATH", tmp_path / "missing.json")
    key, _ = await _register(client)
    assert (await client.get("/api/v1/me/models", headers=_auth(key))).json() == []
    assert (
        await client.get("/api/v1/me/models/stylewriter/default", headers=_auth(key))
    ).status_code == 404


def test_every_route_endpoint_is_nameable():
    """The rate-limit middleware (off under tests) names every route's
    endpoint via __module__ and __name__; an ASGI object without them turns
    every request into a 500 in production but never fails here."""
    from backend.main import app

    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        assert getattr(endpoint, "__module__", None), route
        assert getattr(endpoint, "__name__", None), route
