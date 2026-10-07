"""Real persistence/release checks with the two model boundaries mocked."""

from uuid import UUID

import pytest

from backend.services.rm import workbench as service
from backend.services.rm import workbench_capture as capture
from backend.services.rm import workbench_grader as engine
from backend.tasks import workbench as tasks

from .test_rm_workbench import BASE, account, grade_response, grader, upload

SOURCE_REQUEST = "Repair the CSV import parser and preserve escaped delimiters."
REQUESTS = [
    "Add accessible keyboard navigation to the account settings dialog.",
    "Make invoice totals use exact decimal arithmetic for currency.",
    "Stop the background synchronizer from leaking database connections.",
    "Document the OAuth callback configuration for self hosted installations.",
    "Replace the image thumbnail cache eviction algorithm with LRU.",
]
NEW_PROMPT = "Require recorded test evidence before accepting a passing-test claim."


@pytest.fixture(autouse=True)
def model_and_queue_boundaries(monkeypatch):
    for name in ("reconcile", "assess_trace", "prepare_feedback", "check_change"):
        monkeypatch.setattr(getattr(tasks, name), "delay", lambda *a, **k: None)

    async def abstain(snapshot):
        return capture.CorrectionSignal(correction=False, explanation="No correction in fixture")

    async def original_grade(snapshot):
        return grade_response(snapshot, "meets")

    async def interpret(**kwargs):
        return service.CorrectionDraft(
            change_kind="judge_error",
            proposed_verdict="violates",
            explanation="The human says the test claim is unsupported.",
            title="Require evidence for test claims",
        )

    monkeypatch.setattr(capture, "classify", abstain)
    monkeypatch.setattr(engine, "grade", original_grade)
    monkeypatch.setattr(service.llm, "complete_structured", interpret)


async def dataset(client, pool, requests=None, *, actions=1):
    user = await account(client)
    g = await grader(client, user)
    labels = []
    source = None
    for index, request in enumerate([SOURCE_REQUEST, *(requests or REQUESTS)]):
        messages = [("user", request)]
        messages.extend(("assistant", f"All tests pass for action {i}.") for i in range(actions))
        tid = await upload(client, user, f"comparison-{index}", messages)
        await service.process_trace(tid)
        assessments = await pool.fetch(
            "SELECT * FROM rm_wb_assessments WHERE trace_id=$1 ORDER BY target_index", tid
        )
        assert len(assessments) == actions
        for assessment in assessments:
            feedback = await service.create_feedback(
                user["uuid"],
                {
                    "trace_id": tid,
                    "assessment_id": assessment["id"],
                    "comment": "The recorded evidence does not support this passing test claim.",
                    "proposed_verdict": "violates",
                    "change_kind": "judge_error",
                },
            )
            await service.prepare_feedback(feedback["id"])
            accepted = await service.review_feedback(user["uuid"], feedback["id"], "accept")
            assert accepted["review_status"] == "accepted"
            if index == 0:
                source = source or feedback
            else:
                labels.append(feedback)
    config = {**g["active_version"]["config"], "prompt": NEW_PROMPT}
    cid = await pool.fetchval(
        """INSERT INTO rm_wb_changes
        (owner_user_id,grader_id,feedback_id,kind,title,content,parent_version_id)
        VALUES($1,$2,$3,'grader','Require recorded evidence',$4,$5) RETURNING id""",
        user["uuid"],
        UUID(g["id"]),
        source["id"],
        {"config": config},
        UUID(g["active_version_id"]),
    )
    return user, g, cid, labels


async def check(user, cid):
    await service.request_check(user["uuid"], cid)
    await service.check_change(cid)
    return await service.change_detail(user["uuid"], cid)


def comparison_grade(snapshot):
    return grade_response(snapshot, "violates" if snapshot["prompt"] == NEW_PROMPT else "meets")


async def test_comparison_freezes_both_inputs_before_calls_and_groups_trace_retries(
    client, pool, monkeypatch
):
    requests = [*REQUESTS, REQUESTS[0], REQUESTS[0].replace("dialog", "dialogs"), SOURCE_REQUEST]
    user, g, cid, labels = await dataset(client, pool, requests, actions=2)
    calls = []

    async def grade(snapshot):
        report = await pool.fetchval("SELECT check_report FROM rm_wb_changes WHERE id=$1", cid)
        assert len(report["cases"]) == 5
        assert len({c["trace_id"] for c in report["cases"]}) == 5
        for case in report["cases"]:
            assert (
                case["current_input"]["provider_request"]["state"]
                == case["candidate_input"]["provider_request"]["state"]
            )
            for side in ("current", "candidate"):
                saved = case[f"{side}_input"]
                assert engine.request_hash(saved["provider_request"]) == saved["input_hash"]
        assert any(
            snapshot == c[f"{side}_input"]
            for c in report["cases"]
            for side in ("current", "candidate")
        )
        if snapshot["prompt"] == NEW_PROMPT:
            matching = next(c for c in report["cases"] if c["candidate_input"] == snapshot)
            assert matching["current_output"]["raw_output"] == {"test_response": "meets"}
        calls.append(snapshot)
        return comparison_grade(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    result = await check(user, cid)
    assert result["status"] == "checked", result["error"]
    report = result["check_report"]
    assert report["passed"] and report["total"] == report["corrected"] == 5
    assert report["regressions"] == 0 and len(calls) == 10
    released = await service.release_change(user["uuid"], cid)
    assert released["status"] == "released"
    assert released["version_id"] != UUID(g["active_version_id"])


async def test_failed_candidate_keeps_saved_inputs_and_completed_current_output(
    client, pool, monkeypatch
):
    user, g, cid, labels = await dataset(client, pool, REQUESTS[:1])

    async def grade(snapshot):
        if snapshot["prompt"] == NEW_PROMPT:
            raise engine.GradingError(
                "JEV returned an invalid choice", raw_output={"malformed": True}
            )
        return comparison_grade(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    result = await check(user, cid)
    assert result["status"] == "failed"
    case = result["check_report"]["cases"][0]
    assert case["current_output"]["raw_output"] == {"test_response": "meets"}
    assert case["candidate_output"] == {"malformed": True}
    assert case["candidate_error"] == "JEV returned an invalid choice"
    assert case["current_input"]["input_hash"] != case["candidate_input"]["input_hash"]
    with pytest.raises(ValueError, match="required checks"):
        await service.release_change(user["uuid"], cid)


@pytest.mark.parametrize("mutation", ["reject", "re_review", "label", "new_label"])
async def test_release_revalidates_every_benchmark_review(client, pool, monkeypatch, mutation):
    user, g, cid, labels = await dataset(client, pool)

    async def grade(snapshot):
        return comparison_grade(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    result = await check(user, cid)
    assert result["check_report"]["passed"]
    fid = UUID(result["check_report"]["cases"][-1]["feedback_id"])
    if mutation == "new_label":
        assessment_id = await pool.fetchval(
            "SELECT assessment_id FROM rm_wb_feedback WHERE id=$1", fid
        )
        await service.label_assessment(user["uuid"], assessment_id, "meets")
    else:
        await service.review_feedback(
            user["uuid"],
            fid,
            "reject" if mutation == "reject" else "accept",
            verdict="meets" if mutation == "label" else None,
        )
    with pytest.raises(ValueError, match="comparison label changed"):
        await service.release_change(user["uuid"], cid)
    assert await pool.fetchval(
        "SELECT active_version_id FROM rm_wb_graders WHERE id=$1", UUID(g["id"])
    ) == UUID(g["active_version_id"])


async def test_duplicate_check_dispatch_does_not_start_two_comparisons(client, pool, monkeypatch):
    user, g, cid, labels = await dataset(client, pool, REQUESTS[:1])
    calls = []

    async def grade(snapshot):
        calls.append(snapshot)
        return comparison_grade(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.request_check(user["uuid"], cid)
    with pytest.raises(ValueError, match="not available|already being checked"):
        await service.request_check(user["uuid"], cid)
    import asyncio

    await asyncio.gather(service.check_change(cid), service.check_change(cid))
    assert len(calls) == 2


@pytest.mark.parametrize("basis", ["owner_criteria_edit", "reviewed_correction"])
async def test_changed_requirements_need_explicit_unmeasured_acceptance(
    client, pool, monkeypatch, basis
):
    user = await account(client)
    g = await grader(client, user)
    if basis == "owner_criteria_edit":
        config = {
            **g["active_version"]["config"],
            "criteria": [
                {
                    **g["active_version"]["config"]["criteria"][0],
                    "description": "New requirement: always report the exact test command and its exit status.",
                }
            ],
        }
        change = await service.draft_version(user["uuid"], UUID(g["id"]), config)
    else:
        tid = await upload(client, user)
        await service.process_trace(tid)
        assessment_id = await pool.fetchval(
            "SELECT id FROM rm_wb_assessments WHERE trace_id=$1", tid
        )
        feedback = await service.create_feedback(
            user["uuid"],
            {
                "trace_id": tid,
                "assessment_id": assessment_id,
                "comment": "Going forward always report the exact test command and exit status.",
                "change_kind": "requirement_change",
                "proposed_verdict": None,
            },
        )

        async def requirement_draft(**kwargs):
            return service.CorrectionDraft(
                change_kind="requirement_change",
                proposed_verdict=None,
                explanation="A new reporting requirement, not evidence of an earlier error.",
                title="Report command and exit status",
                grader_prompt=NEW_PROMPT,
            )

        monkeypatch.setattr(service.llm, "complete_structured", requirement_draft)
        await service.prepare_feedback(feedback["id"])
        await service.review_feedback(user["uuid"], feedback["id"], "accept")
        change = (await service.feedback_detail(user["uuid"], feedback["id"]))["changes"][0]

    async def forbidden(snapshot):
        raise AssertionError("Old labels cannot measure changed requirements")

    monkeypatch.setattr(engine, "grade", forbidden)
    checked = await check(user, change["id"])
    report = checked["check_report"]
    assert report["can_accept_unmeasured"] and report["requirement_basis"] == basis
    assert not report["passed"] and not report["quality_measured"] and not report["cases"]
    blocked = await client.post(f"{BASE}/changes/{change['id']}/release", headers=user["headers"])
    assert blocked.status_code == 422
    released = await client.post(
        f"{BASE}/changes/{change['id']}/release",
        headers=user["headers"],
        json={"accept_unmeasured": True},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"
    history = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='released'", UUID(g["id"])
    )
    assert history["accepted_unmeasured"] is True and history["quality_measured"] is False


async def test_unmeasured_flag_cannot_bypass_quality_check_for_manual_prompt_edit(client, pool):
    user = await account(client)
    g = await grader(client, user)
    config = {**g["active_version"]["config"], "prompt": NEW_PROMPT}
    change = await service.draft_version(user["uuid"], UUID(g["id"]), config)
    checked = await check(user, change["id"])
    assert not checked["check_report"].get("can_accept_unmeasured")
    released = await client.post(
        f"{BASE}/changes/{change['id']}/release",
        headers=user["headers"],
        json={"accept_unmeasured": True},
    )
    assert released.status_code == 422
    assert await pool.fetchval(
        "SELECT active_version_id FROM rm_wb_graders WHERE id=$1", UUID(g["id"])
    ) == UUID(g["active_version_id"])
