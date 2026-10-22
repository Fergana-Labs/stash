"""Image evals: examples, training, scoring, the call log, labeling and owner isolation.

The image embedder is replaced by a fake that maps an image's average color to a
vector (reddish vs bluish), and written comments by a stub, so tests exercise the
real SQL, storage, fitting and auth without Modal or Claude.
"""

from io import BytesIO
from uuid import UUID, uuid4

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image

from backend.services.image_eval import build, critic, embedder
from backend.services.image_eval import head as heads

from .conftest import unique_name

DIM = 16


def _png(color: tuple[int, int, int], size=(64, 96)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


RED = [_png((200 + i * 10, 30, 40 + i * 5)) for i in range(5)]
BLUE = [_png((30, 40 + i * 5, 200 + i * 10)) for i in range(5)]


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAGE_EVAL_IMAGE_DIR", str(tmp_path))
    calls = {"embed": 0, "comments": 0}

    async def embed(images):
        calls["embed"] += len(images)
        out = []
        for data in images:
            r, g, b = (
                np.asarray(Image.open(BytesIO(data)).convert("RGB")).reshape(-1, 3).mean(0) / 255
            )
            rng = np.random.default_rng(int(r * 1000 + g * 100 + b * 10))
            out.append(
                (np.array([r - b, b - r] + [0.0] * (DIM - 2)) + rng.normal(0, 0.05, DIM)).tolist()
            )
        return out

    async def comments(classifier_id, name, data, content_type, score):
        calls["comments"] += 1
        return {
            "summary": f"score {score:.2f}",
            "fixes": [{"issue": "too blue", "fix": "use red"}],
            "keep": [],
        }

    monkeypatch.setattr(embedder, "embed", embed)
    monkeypatch.setattr(critic, "comments", comments)
    return calls


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register", json={"name": unique_name("taste"), "password": "securepassword1"}
    )
    assert resp.status_code == 201
    return _auth(resp.json()["api_key"])


async def _upload(client, auth, cid, label, images):
    files = [("files", (f"{label}{i}.png", data, "image/png")) for i, data in enumerate(images)]
    return await client.post(
        f"/api/v1/image-evals/{cid}/examples", headers=auth, data={"label": label}, files=files
    )


async def _trained(client, auth) -> str:
    resp = await client.post("/api/v1/image-evals", headers=auth, json={"name": "Red things"})
    assert resp.status_code == 201
    cid = resp.json()["id"]
    assert (await _upload(client, auth, cid, "liked", RED[:4])).status_code == 201
    assert (await _upload(client, auth, cid, "disliked", BLUE[:4])).status_code == 201
    trained = await client.post(f"/api/v1/image-evals/{cid}/train", headers=auth)
    assert trained.status_code == 200, trained.text
    return cid


async def test_train_and_score(client: AsyncClient, fakes):
    auth = await _register(client)
    cid = await _trained(client, auth)

    detail = (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()
    assert detail["examples"] == {"liked": 4, "disliked": 4, "imitations": 0}
    assert detail["heldout_accuracy"] == 1.0
    assert detail["heldout_method"] == "leave-one-out"
    assert detail["needs_training"] is False

    red = await client.post(
        f"/api/v1/image-evals/{cid}/score",
        headers=auth,
        files={"file": ("x.png", RED[4], "image/png")},
        data={"caller": "draw-agent", "task": "a red cat"},
    )
    blue = await client.post(
        f"/api/v1/image-evals/{cid}/score",
        headers=auth,
        json={
            "image_base64": "data:image/png;base64,"
            + __import__("base64").b64encode(BLUE[4]).decode()
        },
    )
    assert red.status_code == 200 and blue.status_code == 200, (red.text, blue.text)
    assert red.json()["score"] > 0.5 > blue.json()["score"]
    assert red.json()["label"] == "liked"
    assert red.json()["fixes"] == [{"issue": "too blue", "fix": "use red"}]

    calls = (await client.get(f"/api/v1/image-evals/{cid}/calls", headers=auth)).json()["calls"]
    assert [c["caller"] for c in calls][-1] == "draw-agent"
    assert calls[-1]["task"] == "a red cat"
    assert calls[-1]["comments"]["summary"].startswith("score")
    image = await client.get(f"/api/v1/image-evals/{cid}/calls/{calls[0]['id']}/image", headers=auth)
    assert image.status_code == 200 and image.content == BLUE[4]


async def test_comments_can_be_skipped(client: AsyncClient, fakes):
    auth = await _register(client)
    cid = await _trained(client, auth)
    before = fakes["comments"]
    resp = await client.post(
        f"/api/v1/image-evals/{cid}/score",
        headers=auth,
        files={"file": ("x.png", RED[4], "image/png")},
        data={"comments": "false"},
    )
    assert resp.status_code == 200
    assert resp.json()["fixes"] == [] and fakes["comments"] == before


async def test_labeling_a_call_adds_an_example_without_reembedding(client: AsyncClient, fakes):
    auth = await _register(client)
    cid = await _trained(client, auth)
    call = (
        await client.post(
            f"/api/v1/image-evals/{cid}/score",
            headers=auth,
            files={"file": ("x.png", BLUE[4], "image/png")},
        )
    ).json()
    embedded = fakes["embed"]

    resp = await client.put(
        f"/api/v1/image-evals/{cid}/calls/{call['call_id']}/label",
        headers=auth,
        json={"label": "disliked", "note": "colors horribly off"},
    )
    assert resp.status_code == 200
    detail = (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()
    assert detail["examples"] == {"liked": 4, "disliked": 5, "imitations": 0}
    assert detail["needs_training"] is True
    listed = (await client.get(f"/api/v1/image-evals/{cid}/calls", headers=auth)).json()["calls"][0]
    assert (listed["feedback_label"], listed["feedback_note"]) == (
        "disliked",
        "colors horribly off",
    )

    # Relabeling replaces the example; clearing removes it.
    await client.put(
        f"/api/v1/image-evals/{cid}/calls/{call['call_id']}/label", headers=auth, json={"label": "liked"}
    )
    assert (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()["examples"] == {
        "liked": 5,
        "disliked": 4,
        "imitations": 0,
    }
    await client.put(
        f"/api/v1/image-evals/{cid}/calls/{call['call_id']}/label", headers=auth, json={"label": None}
    )
    assert (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()["examples"] == {
        "liked": 4,
        "disliked": 4,
        "imitations": 0,
    }

    assert (await client.post(f"/api/v1/image-evals/{cid}/train", headers=auth)).status_code == 200
    assert fakes["embed"] == embedded


async def test_examples_list_image_and_delete(client: AsyncClient):
    auth = await _register(client)
    cid = await _trained(client, auth)
    examples = (await client.get(f"/api/v1/image-evals/{cid}/examples", headers=auth)).json()["examples"]
    assert len(examples) == 8 and all(e["heldout_score"] is not None for e in examples)
    first = examples[0]
    image = await client.get(f"/api/v1/image-evals/{cid}/examples/{first['id']}/image", headers=auth)
    assert image.status_code == 200 and image.content == RED[0]
    assert (
        await client.delete(f"/api/v1/image-evals/{cid}/examples/{first['id']}", headers=auth)
    ).status_code == 204
    assert (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()["examples"]["liked"] == 3


async def test_rejections(client: AsyncClient):
    auth = await _register(client)
    cid = (await client.post("/api/v1/image-evals", headers=auth, json={"name": "x"})).json()["id"]
    bad = await client.post(
        f"/api/v1/image-evals/{cid}/examples",
        headers=auth,
        data={"label": "liked"},
        files=[("files", ("notes.txt", b"not an image", "text/plain"))],
    )
    assert bad.status_code == 422
    untrained = await client.post(
        f"/api/v1/image-evals/{cid}/score", headers=auth, files={"file": ("x.png", RED[0], "image/png")}
    )
    assert untrained.status_code == 422
    await _upload(client, auth, cid, "liked", RED[:2])
    await _upload(client, auth, cid, "disliked", BLUE[:4])
    too_few = await client.post(f"/api/v1/image-evals/{cid}/train", headers=auth)
    assert too_few.status_code == 422 and "at least 3" in too_few.json()["detail"]


async def test_owner_isolation(client: AsyncClient):
    owner = await _register(client)
    other = await _register(client)
    cid = await _trained(client, owner)
    for method, path in [
        ("get", f"/api/v1/image-evals/{cid}"),
        ("get", f"/api/v1/image-evals/{cid}/examples"),
        ("get", f"/api/v1/image-evals/{cid}/calls"),
        ("post", f"/api/v1/image-evals/{cid}/train"),
        ("delete", f"/api/v1/image-evals/{cid}"),
    ]:
        assert (await getattr(client, method)(path, headers=other)).status_code == 404, path
    scored = await client.post(
        f"/api/v1/image-evals/{cid}/score", headers=other, files={"file": ("x.png", RED[4], "image/png")}
    )
    assert scored.status_code == 404
    assert (await client.get("/api/v1/image-evals", headers=other)).json()["classifiers"] == []


async def test_read_key_can_score_but_not_train(client: AsyncClient):
    owner = await _register(client)
    cid = await _trained(client, owner)
    minted = await client.post(
        "/api/v1/users/me/keys", headers=owner, json={"name": "agent", "access": "read"}
    )
    read = _auth(minted.json()["api_key"])
    scored = await client.post(
        f"/api/v1/image-evals/{cid}/score", headers=read, files={"file": ("x.png", RED[4], "image/png")}
    )
    assert scored.status_code == 200, scored.text
    assert (await client.post(f"/api/v1/image-evals/{cid}/train", headers=read)).status_code == 403


def test_head_scores_are_not_squashed_toward_half():
    """Choosing L2 by log-loss keeps confident, separable data confident."""
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(1, 0.3, (20, 32)), rng.normal(-1, 0.3, (20, 32))])
    y = np.array([1] * 20 + [0] * 20)
    fitted, metrics = heads.train(x, y)
    assert metrics["heldout_accuracy"] == 1.0
    assert heads.predict(fitted, np.full(32, 1.0)) > 0.9
    assert heads.predict(fitted, np.full(32, -1.0)) < 0.1


SVG_RED = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect width="1024" height="1024" fill="#c83040"/><circle cx="500" cy="500" r="200" fill="#e04050"/></svg>'


def test_sanitize_svg_drops_anything_that_loads_or_runs():
    dirty = (
        '<svg><script>alert(1)</script><image href="file:///etc/hosts"/>'
        '<foreignObject><div/></foreignObject><a href="https://x.test">t</a>'
        '<use href="#cat"/><style>@import url(https://x.test/a.css); .a{fill:url(#g)}</style></svg>'
    )
    clean = build.sanitize_svg(dirty)
    for bad in ("script", "<image", "foreignObject", "https://", "@import"):
        assert bad not in clean
    assert 'href="#cat"' in clean and "url(#g)" in clean
    assert len(build.rasterize(SVG_RED)) > 1000


async def test_build_writes_brief_adds_imitations_and_trains(
    client: AsyncClient, monkeypatch, pool
):
    auth = await _register(client)
    resp = await client.post("/api/v1/image-evals", headers=auth, json={"name": "Red things"})
    cid = resp.json()["id"]
    await _upload(client, auth, cid, "liked", RED[:4])
    await _upload(client, auth, cid, "disliked", BLUE[:3])

    async def ask(system, content, max_tokens):
        if "Return only JSON" in system:
            return '{"brief": "- warm reds", "subjects": ["a cat", "a box", "a mug", "a tree"]}'
        return "```svg\n" + SVG_RED + "\n```"

    monkeypatch.setattr(build, "_ask", ask)
    started = []
    from backend.tasks import image_evals as image_eval_tasks

    monkeypatch.setattr(image_eval_tasks.build_classifier, "delay", lambda cid_: started.append(cid_))
    queued = await client.post(f"/api/v1/image-evals/{cid}/build", headers=auth)
    assert queued.status_code == 202 and queued.json()["build"]["stage"] == "queued"
    assert started == [cid]
    assert (await client.post(f"/api/v1/image-evals/{cid}/build", headers=auth)).status_code == 409

    await image_eval_tasks.build_classifier_async(UUID(cid))
    detail = (await client.get(f"/api/v1/image-evals/{cid}", headers=auth)).json()
    assert detail["style_brief"] == "- warm reds"
    assert detail["build"]["stage"] == "done" and detail["build"]["imitations"] == 4
    assert detail["examples"] == {"liked": 4, "disliked": 3, "imitations": 4}
    assert detail["trained"] and not detail["needs_training"]
    examples = (await client.get(f"/api/v1/image-evals/{cid}/examples", headers=auth)).json()["examples"]
    assert sorted(e["filename"] for e in examples if e["source"] == "imitation") == [
        "a box",
        "a cat",
        "a mug",
        "a tree",
    ]


async def test_wizard_image_eval_goes_from_upload_card_to_endpoint(
    client: AsyncClient, monkeypatch, pool
):
    from backend.services.intuition import wizard
    from backend.tasks import image_evals as image_eval_tasks

    auth = await _register(client)
    owner = UUID((await client.get("/api/v1/users/me", headers=auth)).json()["id"])
    session = await wizard.create_session(owner)
    assert wizard._image_intent("Learn Yoko's drawing style from her drawings")
    assert not wizard._image_intent("Flag which brand guidelines a product photo breaks")

    result, card = await wizard.image_tool(owner, session, {"operation": "prepare", "name": "Reds"})
    assert card["kind"] == "image_eval" and card["props"]["section"] == "examples"
    assert wizard._awaits_user(card, result)
    assert [t["name"] for t in await wizard.setup_tools(owner, session)] == ["image_eval"]
    cid = card["props"]["evalId"]
    found = (await client.get(f"/api/v1/image-evals/by-model/{session['model_id']}", headers=auth)).json()
    assert found["id"] == cid and found["name"] == "Reds"

    # Too few images: finish keeps asking for them instead of building.
    result, card = await wizard.image_tool(owner, session, {"operation": "finish"})
    assert card["props"]["section"] == "examples"

    await _upload(client, auth, cid, "liked", RED[:4])
    started = []
    monkeypatch.setattr(image_eval_tasks.build_classifier, "delay", lambda cid_: started.append(cid_))
    result, card = await wizard.image_tool(owner, session, {"operation": "finish"})
    assert result["status"] == "working" and card["props"]["section"] == "progress"
    assert started == [cid]

    async def ask(system, content, max_tokens):
        if "Return only JSON" in system:
            return '{"brief": "- warm reds", "subjects": ["a cat", "a box", "a mug", "a tree"]}'
        return "```svg\n" + SVG_RED + "\n```"

    monkeypatch.setattr(build, "_ask", ask)
    await image_eval_tasks.build_classifier_async(UUID(cid))
    result, card = await wizard.image_tool(owner, session, {"operation": "finish"})
    assert result["published"] is True and card["props"]["section"] == "connect"
    assert result["endpoint"] == f"/api/v1/image-evals/{cid}/score"


async def test_by_model_is_404_for_other_evals(client: AsyncClient):
    auth = await _register(client)
    missing = await client.get(f"/api/v1/image-evals/by-model/{uuid4()}", headers=auth)
    assert missing.status_code == 404
