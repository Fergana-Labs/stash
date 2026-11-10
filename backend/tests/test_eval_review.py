"""Reviewed rubric changes: with approval required, a build proposes a change instead of
saving it, the proposal carries its checks, and only an approval changes the rubric.

Uses the toy world of test_eval_channel.py: red is good, blue and striped are bad, and the
first rubric only knows about color, so striped red work is misjudged until a Stripes trait
is added.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services.evals import proposals, rubric_quality
from backend.tasks import evals as eval_tasks

from .test_eval_channel import (  # noqa: F401 (world is a fixture)
    COLOR,
    STRIPED,
    STRIPES,
    _build,
    _messages,
    _post,
    _register,
    _striped_eval,
    world,
)

ADD_STRIPES = {
    "changes": [{"kind": "add", "trait": "Stripes", "why": "the striped ones are bad"}],
    "traits": [COLOR, STRIPES],
}


@pytest.fixture
def checks_queued(monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(eval_tasks.check_proposal, "delay", queued.append)
    return queued


async def _score(client, auth, eid, image) -> dict:
    resp = await client.post(
        f"/api/v1/evals/{eid}/score",
        headers=auth,
        data={"caller": "support-agent"},
        files={"files": ("x.png", image, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _changes(client, auth, eid) -> dict:
    return (await client.get(f"/api/v1/evals/{eid}/changes", headers=auth)).json()


async def _versions(client, auth, eid) -> list[dict]:
    return (await client.get(f"/api/v1/evals/{eid}/rubric", headers=auth)).json()["versions"]


async def _reviewed_eval(client, auth) -> str:
    """An eval at rubric v1 (color only) that now requires approval of rubric changes."""
    eid = await _striped_eval(client, auth)
    await _build(eid)
    resp = await client.put(f"/api/v1/evals/{eid}/review", headers=auth, json={"required": True})
    assert resp.status_code == 200 and resp.json()["review_required"] is True
    return eid


async def test_a_build_proposes_a_change_with_its_checks_and_approval_applies_it(
    client: AsyncClient,
    world,  # noqa: F811
):
    auth = await _register(client)
    eid = await _reviewed_eval(client, auth)
    # An agent's striped output passes under v1, and the call records the version that scored it.
    before = await _score(client, auth, eid, STRIPED[5])
    assert before["score"] == 1.0 and before["rubric_version"] == 1

    note = (await _post(client, auth, eid, "the striped ones keep passing")).json()["message"]
    world.proposals.append(ADD_STRIPES)
    await _build(eid, reply_to=note["id"])

    # The rubric did not change: the edit is waiting as a proposal.
    detail = (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()
    assert detail["version"] == 1 and detail["open_changes"] == 1
    assert [t["name"] for t in detail["traits"]] == ["Color"]
    assert (await _score(client, auth, eid, STRIPED[4]))["score"] == 1.0

    listed = await _changes(client, auth, eid)
    assert [(p["number"], p["status"], p["base"]) for p in listed["proposals"]] == [(1, "open", 1)]
    proposal = listed["proposals"][0]
    assert proposal["proposed_by"] is None and proposal["source"] == "revised"
    assert proposal["name"] == ""  # unnamed: the page names it after its first edit
    assert proposal["opened_by"]  # the eval's owner, whose examples the build answered
    assert [t["name"] for t in proposal["traits"]] == ["Color", "Stripes"]
    assert [t["name"] for t in proposal["before"]["traits"]] == ["Color"]
    assert proposal["changes"][0] == ADD_STRIPES["changes"][0]
    found = proposal["checks"]
    assert (found["before"]["fit"]["right"], found["after"]["fit"]["right"]) == (6, 8)
    # The two striped examples are fixed, nothing breaks, and each points at a real example.
    assert len(found["fixed"]) == 2 and found["broke"] == []
    assert all(f["id"] in proposal["examples"] for f in found["fixed"])
    assert all(proposal["examples"][f["id"]]["label"] == "bad" for f in found["fixed"])
    # The agent call made under v1 would fail under the proposed rubric.
    assert found["calls"]["n"] == 1 and found["calls"]["pass_before"] == 1
    assert found["calls"]["pass_after"] == 0
    assert found["calls"]["changed"][0]["id"] == before["call_id"]
    # The call names the trait it now scores lowest on (the fake judge fails every trait
    # alike), and the change says in a line how the agent fares under the proposed rubric.
    assert found["calls"]["changed"][0]["low"]["trait"] in ("Color", "Stripes")
    assert found["summary"] == "Striped outputs now fail on Stripes."
    # The rubric verifier graded both rubrics' text on its own traits, each 0-1 with a reason.
    graded = found["rubric_quality"]
    assert (graded["before"]["score"], graded["after"]["score"]) == (0.25, 0.75)
    assert [t["trait"] for t in graded["after"]["traits"]] == [
        t["name"] for t in rubric_quality.TRAITS
    ]
    assert graded["after"]["traits"][0] == {
        "trait": "Checks reasoning, not just a value",
        "score": 0.75,
        "why": "as written",
    }
    assert "1 pass under the rubric in use, 0 under the proposed one" in world.summary_texts[-1]
    assert "1.00 pass -> 0.00 fail; lowest trait now:" in world.summary_texts[-1]
    assert proposal["calls"][before["call_id"]]["caller"] == "support-agent"
    assert found["manipulation"]["resisted"] == found["manipulation"]["n"]
    assert proposal["passed"] is True and proposal["stale"] is False
    assert proposal["quality"]["after"]["score"] > proposal["quality"]["before"]["score"]

    update = (await _messages(client, auth, eid))["messages"][-1]
    assert update["thread_id"] == note["id"] and update["data"]["proposal"] == 1
    assert update["text"] == (
        "Proposed change #1 to rubric v1: added Stripes. It agrees with 8 of 8 examples it "
        "learned from (was 6 of 8). The rubric stays as it is until someone approves it."
    )

    # The same edit proposed again by a later build leaves the waiting proposal alone.
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    assert [p["number"] for p in (await _changes(client, auth, eid))["proposals"]] == [1]

    approved = await client.post(
        f"/api/v1/evals/{eid}/changes/{proposal['id']}/approve",
        headers=auth,
        json={"note": "matches what support flagged"},
    )
    assert approved.status_code == 200, approved.text
    decided = approved.json()["proposals"][0]
    assert decided["status"] == "approved" and decided["version"] == 2
    assert decided["decided_by"] and decided["note"] == "matches what support flagged"

    versions = await _versions(client, auth, eid)
    assert [(v["number"], v["source"]) for v in versions] == [(2, "revised"), (1, "written")]
    assert versions[0]["approved"]["proposal"] == 1
    assert versions[0]["approved"]["by"] == decided["decided_by"]
    assert versions[0]["metrics"]["fit"]["right"] == 8 and versions[0]["quality"]["score"] == 100
    # v1 is the version that scored both calls so far.
    assert versions[1]["used"]["calls"] == 2 and versions[1]["used"]["callers"] == ["support-agent"]
    assert versions[0]["used"] is None
    after = await _score(client, auth, eid, STRIPED[5])
    assert after["score"] == 0.0 and after["rubric_version"] == 2
    calls = (await client.get(f"/api/v1/evals/{eid}/calls", headers=auth)).json()["calls"]
    assert [c["rubric_version"] for c in calls] == [2, 1, 1]
    # The decision is reported in the thread the evidence came from.
    last = (await _messages(client, auth, eid))["messages"][-1]
    assert last["thread_id"] == note["id"]
    assert last["text"].startswith("Proposed change #1 approved: now rubric v2")

    again = await client.post(
        f"/api/v1/evals/{eid}/changes/{proposal['id']}/approve", headers=auth, json={}
    )
    assert again.status_code == 409


async def test_a_rejected_change_is_not_proposed_again(client: AsyncClient, world):  # noqa: F811
    auth = await _register(client)
    eid = await _reviewed_eval(client, auth)
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    proposal = (await _changes(client, auth, eid))["proposals"][0]

    rejected = await client.post(
        f"/api/v1/evals/{eid}/changes/{proposal['id']}/reject",
        headers=auth,
        json={"note": "stripes are fine for charts"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["proposals"][0]["status"] == "rejected"
    assert (await _versions(client, auth, eid))[0]["number"] == 1

    # The next build tells the reviser what was turned down, and the same edit isn't reopened.
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    assert 'rejected by the reviewer: "stripes are fine for charts"' in world.proposer_texts[-1]
    listed = await _changes(client, auth, eid)
    assert [(p["number"], p["status"]) for p in listed["proposals"]] == [(1, "rejected")]
    detail = (await client.get(f"/api/v1/evals/{eid}", headers=auth)).json()
    assert detail["version"] == 1 and detail["open_changes"] == 0


async def test_a_persons_edit_is_proposed_and_goes_stale_when_the_rubric_moves(
    client: AsyncClient,
    world,  # noqa: F811
    checks_queued,
):
    auth = await _register(client)
    eid = await _reviewed_eval(client, auth)
    mine = {"name": "Color", "good": "warm red, never orange", "bad": "blue"}
    resp = await client.put(
        f"/api/v1/evals/{eid}/rubric", headers=auth, json={"traits": [mine], "base": 1}
    )
    assert resp.status_code == 200, resp.text
    assert [v["number"] for v in resp.json()["versions"]] == [1]  # nothing saved
    edit = (await _changes(client, auth, eid))["proposals"][0]
    assert edit["proposed_by"] and edit["source"] == "edited"
    assert edit["opened_by"] == edit["proposed_by"]
    assert edit["checks"] is None and edit["passed"] is None
    assert checks_queued == [edit["id"]]

    await proposals.run_checks(UUID(edit["id"]))
    edit = (await _changes(client, auth, eid))["proposals"][0]
    assert edit["checks"]["before"]["fit"]["right"] == 6 and edit["passed"] is True

    # The build's own change is approved first, so the edit was made on an old version.
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    listed = (await _changes(client, auth, eid))["proposals"]
    assert [(p["number"], p["proposed_by"] is None) for p in listed] == [(2, True), (1, False)]
    assert (
        await client.post(
            f"/api/v1/evals/{eid}/changes/{listed[0]['id']}/approve", headers=auth, json={}
        )
    ).status_code == 200
    edit = next(p for p in (await _changes(client, auth, eid))["proposals"] if p["number"] == 1)
    assert edit["status"] == "open" and edit["stale"] is True
    refused = await client.post(
        f"/api/v1/evals/{eid}/changes/{edit['id']}/approve", headers=auth, json={}
    )
    assert refused.status_code == 409
    assert (await _versions(client, auth, eid))[0]["number"] == 2


async def test_without_review_a_build_saves_versions_as_before(client: AsyncClient, world):  # noqa: F811
    auth = await _register(client)
    eid = await _striped_eval(client, auth)
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    listed = await _changes(client, auth, eid)
    assert listed == {"review_required": False, "proposals": []}
    versions = await _versions(client, auth, eid)
    assert [v["number"] for v in versions] == [2, 1]
    assert versions[0]["approved"] is None and versions[0]["created_by"] is None

    # A direct edit records who made it.
    mine = {"name": "Color", "good": "warm red", "bad": "blue"}
    edited = await client.put(
        f"/api/v1/evals/{eid}/rubric", headers=auth, json={"traits": [mine, STRIPES], "base": 2}
    )
    assert edited.json()["versions"][0]["created_by"]


async def test_a_change_is_discussed_before_and_after_it_is_decided(
    client: AsyncClient,
    world,  # noqa: F811
):
    auth = await _register(client)
    eid = await _reviewed_eval(client, auth)
    world.proposals.append(ADD_STRIPES)
    await _build(eid)
    proposal = (await _changes(client, auth, eid))["proposals"][0]
    assert proposal["comments"] == []
    url = f"/api/v1/evals/{eid}/changes/{proposal['id']}/comments"

    whole = await client.post(url, headers=auth, json={"body": " is this too strict? "})
    assert whole.status_code == 200, whole.text
    on_trait = await client.post(
        url, headers=auth, json={"body": "thin pinstripes too?", "trait": "Stripes"}
    )
    comments = on_trait.json()["proposals"][0]["comments"]
    assert [(c["body"], c["trait"]) for c in comments] == [
        ("is this too strict?", ""),
        ("thin pinstripes too?", "Stripes"),
    ]
    assert all(c["author"] for c in comments)
    assert (await client.post(url, headers=auth, json={"body": "   "})).status_code == 422

    # A decided change can still be commented on, and keeps its comments.
    await client.post(f"/api/v1/evals/{eid}/changes/{proposal['id']}/reject", headers=auth, json={})
    after = await client.post(url, headers=auth, json={"body": "revisit next quarter"})
    assert [c["body"] for c in after.json()["proposals"][0]["comments"]][
        -1
    ] == "revisit next quarter"

    # Someone else's eval is not found.
    other = await _register(client)
    assert (await client.post(url, headers=other, json={"body": "hi"})).status_code == 404
