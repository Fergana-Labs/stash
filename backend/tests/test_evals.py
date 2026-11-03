"""Judge evals: examples marked good or bad, a build that writes traits and checks itself,
and one endpoint that scores an agent's trace and output with a grade per trait.

Object storage is a dict and Claude is a fake that grades by color: a submission whose
last image is red gets 5 on every trait, a blue one gets 1.
"""

import base64
import json
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image

from backend.services import storage_service
from backend.services.evals import build, judge, robustness
from backend.tasks import evals as eval_tasks

from .conftest import unique_name


def _png(color, size=(64, 64)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


RED = [_png((210 + i * 8, 30, 40)) for i in range(5)]
BLUE = [_png((30, 40, 210 + i * 8)) for i in range(5)]
TRAITS = {
    "summary": "Red things",
    "traits": [
        {"name": "Color", "good": "red", "bad": "blue"},
        {"name": "Shape", "good": "square", "bad": "round"},
    ],
}


def _redness(block: dict) -> float:
    data = base64.b64decode(block["source"]["data"])
    r, _, b = np.asarray(Image.open(BytesIO(data)).convert("RGB")).reshape(-1, 3).mean(0)
    return r - b


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    store: dict[str, bytes] = {}
    calls = {"judge": 0, "traits": 0, "systems": [], "excluded": [], "changes": []}

    async def upload_file(owner, name, content, ctype):
        key = f"{owner}/{uuid4().hex}/{name}"
        store[key] = content
        return key

    async def download_file(key):
        return store[key]

    class Messages:
        async def create(self, *, model, max_tokens, system, messages):
            content = messages[0]["content"]
            if system.startswith(robustness.SYSTEM[:40]):
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text='{"attempts": []}')]
                )
            if system.startswith(judge.CHANGE_SYSTEM[:60]):
                calls["changes"].append(content)
                after = next(
                    i
                    for i, b in enumerate(content)
                    if b.get("text") == "The work after the change:"
                )
                images = [b for b in content[after:] if b["type"] == "image"]
                if not images:
                    traits = [
                        {"trait": "Color", "touched": False, "score": None, "why": "no image"},
                        {"trait": "Shape", "touched": False, "score": None, "why": "no image"},
                    ]
                else:
                    red = _redness(images[-1]) > 0
                    traits = [
                        # A worse change graded 4: the judge forgetting the prompt's cap.
                        {
                            "trait": "Color",
                            "touched": True,
                            "score": 5 if red else 4,
                            "effect": "better" if red else "worse",
                            "why": "red" if red else "blue",
                        },
                        {
                            "trait": "Shape",
                            "touched": False,
                            "score": None,
                            "effect": None,
                            "why": "unchanged",
                        },
                    ]
                text = json.dumps(
                    {"traits": traits, "summary": "the change", "fixes": [], "keep": []}
                )
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
            if system == build.TRAITS_SYSTEM:
                calls["traits"] += 1
                text = json.dumps(TRAITS)
            else:
                calls["judge"] += 1
                calls["systems"].append(system)
                start = next(
                    i for i, b in enumerate(content) if b.get("text") == "The submission to judge:"
                )
                images = [b for b in content[start:] if b["type"] == "image"]
                grade = (5 if _redness(images[-1]) > 0 else 1) if images else 3
                text = json.dumps(
                    {
                        "traits": [
                            {
                                "trait": "Color",
                                "score": grade,
                                "why": "red" if grade == 5 else "blue",
                            },
                            {"trait": "Shape", "score": grade, "why": "ok"},
                        ],
                        "summary": f"graded {grade}",
                        "fixes": [{"issue": "too blue", "fix": "use red"}],
                        "keep": [],
                    }
                )
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    monkeypatch.setattr(storage_service, "upload_file", upload_file)
    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr(judge.llm, "_get_client", lambda: SimpleNamespace(messages=Messages()))
    monkeypatch.setattr(judge.settings, "EVAL_JUDGE_SAMPLES", 1)
    monkeypatch.setattr(eval_tasks.build_eval, "apply_async", lambda *a, **k: None)
    monkeypatch.setattr(eval_tasks.read_channel, "delay", lambda *a, **k: None)
    return calls


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register", json={"name": unique_name("ev"), "password": "securepassword1"}
    )
    assert resp.status_code == 201
    return _auth(resp.json()["api_key"])


async def _upload(client, auth, eid, label, images, **form):
    files = [("files", (f"{label}{i}.png", data, "image/png")) for i, data in enumerate(images)]
    return await client.post(
        f"/api/v1/evals/{eid}/examples", headers=auth, data={"label": label, **form}, files=files
    )


async def _built(client, auth, *, bad=True) -> str:
    eid = (await client.post("/api/v1/evals", headers=auth, json={"name": "Red things"})).json()[
        "id"
    ]
    assert (await _upload(client, auth, eid, "good", RED[:4])).status_code == 201
    if bad:
        assert (await _upload(client, auth, eid, "bad", BLUE[:3])).status_code == 201
    assert (await client.post(f"/api/v1/evals/{eid}/build", headers=auth)).status_code == 202
    await eval_tasks.build_eval_async(UUID(eid))
    return eid


async def test_examples_build_and_score_with_an_explanation(client: AsyncClient, fakes):
    auth = await _register(client)
    eid = await _built(client, auth)

    detail = (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()
    assert detail["ready"] and detail["examples"] == {"good": 4, "bad": 3}
    assert [t["name"] for t in detail["traits"]] == ["Color", "Shape"]
    assert detail["build"]["summary"] == "Red things"
    # Each example was graded with itself left out of the references, and all were right.
    # Seven examples are too few to hold any out (service.HOLDOUT_AFTER).
    assert detail["build"]["metrics"] == {
        "checked": 7,
        "agreement": 1.0,
        "good_above_bad": 1.0,
        "held_out": {"n": 0, "right": 0, "agreement": None, "good_above_bad": None},
    }
    assert detail["version"] == 1
    assert all(
        "Use exactly these traits" in s and "Color: good = red" in s for s in fakes["systems"]
    )

    red = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        json={
            "trace": [{"role": "user", "content": "Draw a red square"}],
            "output": {"text": "Here it is", "images": [base64.b64encode(RED[4]).decode()]},
            "caller": "draw-agent",
        },
    )
    assert red.status_code == 200, red.text
    body = red.json()
    assert body["score"] == 1.0 and body["explanation"] == "graded 5"
    assert body["traits"][0] == {"trait": "Color", "score": 1.0, "why": "red"}
    assert body["fixes"] == [{"issue": "too blue", "fix": "use red"}]

    blue = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        files={"files": ("x.png", BLUE[4], "image/png")},
        data={"trace": json.dumps([{"role": "user", "content": "Draw"}]), "caller": "draw-agent"},
    )
    assert blue.status_code == 200 and blue.json()["score"] == 0.0

    calls = (await client.get(f"/api/v1/evals/{eid}/calls", headers=auth)).json()["calls"]
    assert [c["score"] for c in calls] == [0.0, 1.0]
    assert calls[1]["input"]["trace"] == [{"role": "user", "content": "Draw a red square"}]
    image = await client.get(f"/api/v1/evals/{eid}/calls/{calls[0]['id']}/files/0", headers=auth)
    assert image.status_code == 200 and image.content == BLUE[4]


async def test_labeling_a_call_makes_it_an_example_and_clearing_removes_it(client: AsyncClient):
    auth = await _register(client)
    eid = await _built(client, auth)
    call = (
        await client.post(
            f"/api/v1/evals/{eid}/score", headers=auth, json={"output": {"text": "plain answer"}}
        )
    ).json()
    assert call["score"] == 0.5  # no image: the fake grades 3

    def put(label, note=""):
        return client.put(
            f"/api/v1/evals/{eid}/calls/{call['call_id']}/label",
            headers=auth,
            json={"label": label, "note": note},
        )

    assert (await put("bad", "too generic")).json()["label"] == "bad"
    detail = (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()
    assert detail["examples"] == {"good": 4, "bad": 4}
    listed = (await client.get(f"/api/v1/evals/{eid}/calls", headers=auth)).json()["calls"][0]
    assert listed["label"] == "bad" and listed["note"] == "too generic"
    examples = (await client.get(f"/api/v1/evals/{eid}/examples", headers=auth)).json()["examples"]
    assert any(e["note"] == "too generic" and e["source"] == "production" for e in examples)

    await put(None)
    assert (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()["examples"] == {
        "good": 4,
        "bad": 3,
    }


async def test_text_and_trace_examples_and_only_good_examples(client: AsyncClient, fakes):
    auth = await _register(client)
    eid = (
        await client.post(
            "/api/v1/evals",
            headers=auth,
            json={"name": "PRs", "instructions": "Is this PR ready to merge?"},
        )
    ).json()["id"]
    trace = [
        {"role": "user", "content": "Fix the login bug"},
        {"role": "assistant", "content": "Patched auth.py", "tool_name": "edit"},
    ]
    resp = await client.post(
        f"/api/v1/evals/{eid}/examples",
        headers=auth,
        data={
            "label": "good",
            "text": "diff --git ...",
            "trace": json.dumps(trace),
            "note": "small and tested",
        },
    )
    assert resp.status_code == 201
    item = resp.json()["examples"][0]["item"]
    assert item["trace"][1] == {
        "role": "assistant",
        "content": "Patched auth.py",
        "tool_name": "edit",
    }
    assert item["text"] == "diff --git ..."

    # Only good examples: the build writes traits and skips the agreement check.
    assert (await client.post(f"/api/v1/evals/{eid}/build", headers=auth)).status_code == 202
    await eval_tasks.build_eval_async(UUID(eid))
    detail = (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()
    assert detail["ready"] and detail["build"]["metrics"]["checked"] == 0
    assert detail["instructions"] == "Is this PR ready to merge?"
    assert fakes["judge"] == 0


async def test_errors_are_explicit(client: AsyncClient, monkeypatch):
    auth = await _register(client)
    eid = (await client.post("/api/v1/evals", headers=auth, json={"name": "x"})).json()["id"]
    assert (
        await client.post(f"/api/v1/evals/{eid}/build", headers=auth)
    ).status_code == 422  # no good examples
    assert (
        await client.post(
            f"/api/v1/evals/{eid}/score", headers=auth, json={"output": {"text": "x"}}
        )
    ).status_code == 409  # not built
    bad_file = await client.post(
        f"/api/v1/evals/{eid}/examples",
        headers=auth,
        data={"label": "good"},
        files=[("files", ("x.bin", b"\x00\x01", "application/octet-stream"))],
    )
    assert bad_file.status_code == 422 and "images, PDFs or text files" in bad_file.json()["detail"]

    built = await _built(client, auth)

    async def down(*a, **k):
        raise judge.JudgeUnavailable("Couldn't score this right now; try again")

    monkeypatch.setattr(judge, "grade", down)
    resp = await client.post(
        f"/api/v1/evals/{built}/score", headers=auth, json={"output": {"text": "x"}}
    )
    assert resp.status_code == 503  # never a made-up number


async def test_evals_are_private_and_separate_from_fitted_intuitions(client: AsyncClient):
    owner = await _register(client)
    other = await _register(client)
    eid = await _built(client, owner)
    assert (await client.get(f"/api/v1/evals/{eid}", headers=other)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/evals/{eid}/score", headers=other, json={"output": {"text": "x"}}
        )
    ).status_code == 404
    assert [
        e["id"] for e in (await client.get("/api/v1/evals", headers=other)).json()["evals"]
    ] == []
    # A fitted intuition is not an eval here.
    fitted = await client.post(
        "/api/v1/intuitions",
        headers=owner,
        json={
            "name": "Router",
            "output_type": "choice",
            "description": "Route tickets",
            "labels": [
                {"id": "billing", "description": "money"},
                {"id": "bugs", "description": "broken"},
            ],
            "rubric": [],
        },
    )
    if fitted.status_code == 201:
        fid = fitted.json()["model"]["id"]
        assert (await client.get(f"/api/v1/evals/{fid}", headers=owner)).status_code == 404


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def test_a_change_is_graded_on_what_it_touched(client: AsyncClient, fakes):
    auth = await _register(client)
    eid = await _built(client, auth)
    resp = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        json={
            "change": "Asked: make the square red. Diff: fill blue -> red",
            "before": {"images": [_b64(BLUE[4])]},
            "output": {"images": [_b64(RED[4])]},
            "caller": "pr-bot",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "change"
    # Shape wasn't touched: it has no grade and doesn't count toward the score.
    assert body["traits"] == [
        {"trait": "Color", "touched": True, "score": 1.0, "effect": "better", "why": "red"},
        {"trait": "Shape", "touched": False, "score": None, "effect": None, "why": "unchanged"},
    ]
    assert body["score"] == 1.0
    # The judge saw the work before, the change, and the work after, in that order.
    content = fakes["changes"][-1]
    texts = [b.get("text", "") for b in content]
    before = texts.index("The work before the change:")
    change = next(i for i, t in enumerate(texts) if t.startswith("The change ("))
    after = texts.index("The work after the change:")
    assert before < change < after
    assert "fill blue -> red" in texts[change]
    # The call keeps the change and the before work alongside the output.
    call = (await client.get(f"/api/v1/evals/{eid}/calls", headers=auth)).json()["calls"][0]
    assert call["input"]["change"].startswith("Asked: make the square red")
    assert len(call["input"]["before"]["files"]) == 1


async def test_a_change_that_makes_a_trait_worse_grades_at_most_2(client: AsyncClient):
    auth = await _register(client)
    eid = await _built(client, auth)
    resp = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        files={
            "files": ("after.png", BLUE[4], "image/png"),
            "before_files": ("before.png", RED[4], "image/png"),
        },
        data={"change": "recolor"},
    )
    assert resp.status_code == 200, resp.text
    color = resp.json()["traits"][0]
    # The fake judge graded it 4 while calling it worse; the cap holds anyway.
    assert color["effect"] == "worse" and color["score"] == 0.25
    assert resp.json()["score"] == 0.25


async def test_a_change_that_touches_no_trait_passes(client: AsyncClient):
    auth = await _register(client)
    eid = await _built(client, auth)
    resp = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        json={"change": "Fixed a typo in the caption", "output": {"text": "caption"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["score"] == 1.0
    assert all(not t["touched"] and t["score"] is None for t in body["traits"])


async def test_without_a_change_the_whole_output_is_graded_as_before(client: AsyncClient, fakes):
    auth = await _register(client)
    eid = await _built(client, auth)
    resp = await client.post(
        f"/api/v1/evals/{eid}/score", headers=auth, json={"output": {"images": [_b64(RED[4])]}}
    )
    assert resp.status_code == 200 and "mode" not in resp.json()
    assert not fakes["changes"]


async def test_a_bad_before_image_names_the_before_field(client: AsyncClient):
    auth = await _register(client)
    eid = await _built(client, auth)
    resp = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        json={"before": {"images": ["not base64!"]}, "output": {"text": "x"}},
    )
    assert resp.status_code == 422 and "before.images[0]" in resp.text


def test_combining_change_grades_takes_the_majority_and_breaks_ties_toward_worse():
    rubric = [{"name": "Color"}, {"name": "Shape"}]

    def g(color, shape):
        return {"score": 0, "traits": [color, shape], "explanation": "", "fixes": [], "keep": []}

    def t(name, touched, score=None, effect=None):
        return {"trait": name, "touched": touched, "score": score, "effect": effect, "why": name}

    graded = [
        g(t("Color", True, 1.0, "better"), t("Shape", True, 0.0, "worse")),
        g(t("Color", True, 0.25, "worse"), t("Shape", False)),
        g(t("Color", False), t("Shape", False)),
    ]
    out = judge.combine_change(graded, "mean", rubric)
    color, shape = out["traits"]
    # Color: touched by 2 of 3 calls; middle of 1.0 and 0.25; one better, one worse -> worse.
    assert color["touched"] and color["score"] == 0.625 and color["effect"] == "worse"
    # Shape: touched by only 1 of 3 calls, so it doesn't count.
    assert not shape["touched"] and shape["score"] is None
    assert out["score"] == 0.625


def test_a_change_grade_explains_itself_with_the_sample_matching_its_score():
    rubric = [{"name": "Color"}, {"name": "Shape"}]

    def t(name, score):
        return {"trait": name, "touched": True, "score": score, "effect": "same", "why": name}

    def g(words, stored, *traits):
        return {
            "score": stored,
            "traits": list(traits),
            "explanation": words,
            "fixes": [],
            "keep": [],
        }

    graded = [
        # A made-up trait lifts A's stored mean to 0.75, though by the rubric's rule it's 0.25.
        g("A", 0.75, t("Color", 0.25), t("Shape", 1.0), t("Extra", 1.0)),
        g("B", 0.75, t("Color", 0.75), t("Shape", 0.75)),
        g("C", 0.5, t("Color", 0.25), t("Shape", 0.75)),
    ]
    out = judge.combine_change(graded, "lowest", rubric)
    assert out["score"] == 0.25
    # A and C both grade 0.25 by the rule; the stored means would have picked C.
    assert out["explanation"] == "A"
