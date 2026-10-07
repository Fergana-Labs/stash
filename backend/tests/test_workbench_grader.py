"""Pure workbench input/adapter checks; all HTTP is mocked, no inference or database."""

import copy
import json

import httpx
import pytest

from backend.services.rm import workbench_grader as grader


def config():
    return {"criteria": copy.deepcopy(grader.DEFAULT_CRITERIA)}


def events():
    return [
        {"id": "s0", "idx": 0, "role": "system", "content": "Be accurate"},
        {"id": "s1", "idx": 1, "role": "user", "content": "Fix the parser and run tests"},
        {
            "id": "s2",
            "idx": 2,
            "role": "assistant",
            "content": "",
            "tool_name": "exec",
            "tool_input": {"cmd": "pytest"},
            "tool_call_id": "call1",
        },
        {
            "id": "s3",
            "idx": 3,
            "role": "tool",
            "content": "exit code 1; 1 failed",
            "tool_call_id": "call1",
        },
        {"id": "s4", "idx": 4, "role": "assistant", "content": "All tests passed"},
        {"id": "s5", "idx": 5, "role": "user", "content": "FUTURE_CORRECTION: they failed"},
    ]


def snapshot():
    steps = events()
    return grader.build_input(steps, steps[4], config())


def response():
    return {
        "model": "jev-1.13.0",
        "answers": {
            c["id"]: {
                "type": "choice",
                "choice": "violates",
                "confidence": 0.85,
                "probabilities": {
                    "meets": 0.05,
                    "violates": 0.9,
                    "insufficient_evidence": 0.04,
                    "not_applicable": 0.01,
                },
            }
            for c in grader.DEFAULT_CRITERIA
        },
        "usage": {"input_tokens": 750, "output_tokens": 20},
    }


def test_snapshot_includes_captured_tool_evidence_and_excludes_future_feedback():
    data = snapshot()
    encoded = json.dumps(data["provider_request"])
    assert "exit code 1; 1 failed" in encoded
    assert "pytest" in encoded
    assert "FUTURE_CORRECTION" not in json.dumps(data)
    assert data["excluded_after_cutoff_count"] == 1
    assert data["evidence_cutoff"] == {"step_id": "s4", "step_index": 4}
    assert data["omissions"] == []
    assert data["input_hash"] == snapshot()["input_hash"]


def test_tool_action_does_not_see_its_future_result():
    steps = events()
    data = grader.build_input(steps, steps[2], config())
    assert "exit code" not in json.dumps(data)
    assert [e["id"] for e in data["context_events"]] == ["s0", "s1", "s2"]


def test_appending_future_events_does_not_change_existing_assessment_input():
    steps = events()
    first = grader.build_input(steps[:5], steps[4], config())
    later = grader.build_input(steps, steps[4], config())
    assert first["provider_request"] == later["provider_request"]
    assert first["input_hash"] == later["input_hash"]


def test_candidate_configuration_preserves_the_exact_frozen_state():
    original = snapshot()
    before = copy.deepcopy(original)
    changed = {
        **config(),
        "prompt": "Inspect recorded failures carefully.",
        "max_context_chars": 2000,
    }
    candidate = grader.with_config(original, changed)
    assert candidate["provider_request"]["state"] == original["provider_request"]["state"]
    for field in ("context_events", "omissions", "evidence_cutoff", "max_context_chars"):
        assert candidate[field] == original[field]
    assert candidate["input_hash"] != original["input_hash"]
    assert candidate["comparison_source_input_hash"] == original["input_hash"]
    assert candidate["prompt"] == changed["prompt"]
    assert "pytest" in json.dumps(candidate["provider_request"]["state"])
    assert original == before
    candidate["context_events"][0]["content"] = "independent mutation"
    assert original == before


def test_same_configuration_comparison_has_same_provider_input_hash():
    original = snapshot()
    assert grader.with_config(original, config())["input_hash"] == original["input_hash"]


def test_candidate_config_cannot_use_a_modified_original_request():
    original = snapshot()
    original["provider_request"]["state"]["events"] = []
    with pytest.raises(ValueError, match="changed"):
        grader.with_config(original, config())


def test_target_is_loaded_from_recorded_event_not_caller_supplied_content():
    steps = events()
    target = {**steps[4], "content": "FAKE_SUCCESS"}
    assert "FAKE_SUCCESS" not in json.dumps(grader.build_input(steps, target, config()))


def test_context_omissions_are_explicit_and_target_stays_present():
    steps = [
        {
            "id": f"s{i}",
            "index": i,
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"START{i}" + "x" * 5000 + f"END{i}",
        }
        for i in range(40)
    ]
    data = grader.build_input(steps, steps[-1], {**config(), "max_context_chars": 2000})
    assert data["target_step_id"] in [e["id"] for e in data["context_events"]]
    assert any(o.get("entire_event") for o in data["omissions"])
    assert any(o.get("field") == "content" for o in data["omissions"])
    assert "[content omitted]" in data["context_events"][0]["content"]
    assert "START39" in data["context_events"][0]["content"]
    assert "END39" in data["context_events"][0]["content"]
    assert len(json.dumps(data["provider_request"]).encode()) < grader.MAX_REQUEST_BYTES


def test_examples_are_scoped_to_criterion_and_detached_from_config():
    cfg = config()
    cfg["examples"] = [
        {
            "criterion_id": "test_reporting",
            "input": "Tests failed; claims pass",
            "verdict": "violates",
            "note": "Report the recorded failure",
        }
    ]
    steps = events()
    data = grader.build_input(steps, steps[4], cfg)
    questions = data["provider_request"]["questions"]
    assert len(questions["test_reporting"]["instructions"]["examples"]) == 1
    assert questions["instruction_adherence"]["instructions"]["examples"] == []
    cfg["examples"][0]["input"] = "later mutation"
    assert "later mutation" not in json.dumps(data)
    assert (
        "untrusted recorded data" in questions["test_reporting"]["instructions"]["evaluation_rules"]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"criteria": [grader.DEFAULT_CRITERIA[0], grader.DEFAULT_CRITERIA[0]]},
        {"criteria": []},
        {"examples": [{"criterion_id": "missing", "input": "x", "verdict": "meets"}]},
        {"examples": [{"criterion_id": "test_reporting", "input": {}, "verdict": "meets"}]},
        {"base_url": "https://other.example"},
        {"prompt": "   "},
        {"max_context_chars": True},
    ],
)
def test_invalid_configs_fail_before_inference(change):
    with pytest.raises(ValueError):
        grader.validate_config({**config(), **change})


def test_target_and_event_identity_must_be_valid():
    steps = events()
    for target in [{**steps[4], "id": "missing"}, {**steps[4], "idx": 99}, steps[3]]:
        with pytest.raises(ValueError):
            grader.build_input(steps, target, config())
    with pytest.raises(ValueError, match="unique"):
        grader.build_input([*steps, steps[0]], steps[4], config())


def test_provider_probabilities_are_not_presented_as_generated_citations_or_reason():
    raw = response()
    parsed = grader.parse_response(raw, [c["id"] for c in grader.DEFAULT_CRITERIA])
    assert parsed["raw_output"] == raw
    assert parsed["usage"] == raw["usage"]
    assert parsed["results"][0] == {
        "criterion_id": "test_reporting",
        "verdict": "violates",
        "reason": None,
        "evidence_step_ids": [],
        "confidence": 0.85,
        "probabilities": raw["answers"]["test_reporting"]["probabilities"],
    }


@pytest.mark.parametrize(
    "malformation",
    [
        "missing_answer",
        "extra_answer",
        "bad_choice",
        "non_string_choice",
        "nan",
        "enormous_integer",
        "negative",
        "missing_probability",
        "invalid_sum",
        "wrong_winner",
        "bad_confidence",
        "bad_usage",
        "bad_model",
    ],
)
def test_malformed_provider_response_is_execution_failure(malformation):
    raw = response()
    answer = raw["answers"]["test_reporting"]
    if malformation == "missing_answer":
        del raw["answers"]["test_reporting"]
    elif malformation == "extra_answer":
        raw["answers"]["unknown"] = answer
    elif malformation == "bad_choice":
        answer["choice"] = "perfect"
    elif malformation == "non_string_choice":
        answer["choice"] = ["meets"]
    elif malformation == "nan":
        answer["probabilities"]["meets"] = float("nan")
    elif malformation == "enormous_integer":
        answer["probabilities"]["meets"] = 10**1000
    elif malformation == "negative":
        answer["probabilities"]["meets"] = -1
    elif malformation == "missing_probability":
        del answer["probabilities"]["meets"]
    elif malformation == "invalid_sum":
        answer["probabilities"]["meets"] = 0.8
    elif malformation == "wrong_winner":
        answer["choice"] = "meets"
    elif malformation == "bad_confidence":
        answer["confidence"] = True
    elif malformation == "bad_usage":
        raw["usage"]["input_tokens"] = -1
    elif malformation == "bad_model":
        raw["model"] = ""
    with pytest.raises(grader.GradingError) as error:
        grader.parse_response(raw, [c["id"] for c in grader.DEFAULT_CRITERIA])
    assert error.value.raw_output == raw


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(grader.settings, "TYPESAFE_API_KEY", "test-only-key")
    monkeypatch.setattr(
        grader.httpx,
        "AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )


async def test_exact_frozen_request_sent_and_real_resolved_model_retained(monkeypatch):
    data = snapshot()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    mock_http(monkeypatch, handler)
    result = await grader.grade(data)
    assert len(requests) == 1
    assert str(requests[0].url) == grader.JEV_ENDPOINT
    assert json.loads(requests[0].content) == data["provider_request"]
    assert result["model"] == "jev-1.13.0"
    assert result["duration_ms"] >= 0


async def test_missing_key_and_changed_snapshot_do_not_send_requests(monkeypatch):
    mock_http(monkeypatch, lambda r: pytest.fail("Must not contact Jev"))
    monkeypatch.setattr(grader.settings, "TYPESAFE_API_KEY", None)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        await grader.grade(snapshot())
    monkeypatch.setattr(grader.settings, "TYPESAFE_API_KEY", "test-only-key")
    data = snapshot()
    data["provider_request"]["model"] = "something-else"
    with pytest.raises(ValueError, match="changed"):
        await grader.grade(data)


@pytest.mark.parametrize("status,retryable", [(401, False), (422, False), (429, True), (529, True)])
async def test_http_failure_is_not_an_agent_verdict_and_does_not_expose_body(
    monkeypatch, status, retryable
):
    mock_http(monkeypatch, lambda r: httpx.Response(status, text="PRIVATE_INPUT"))
    with pytest.raises(grader.GradingError) as error:
        await grader.grade(snapshot())
    assert error.value.retryable is retryable
    assert str(status) in str(error.value)
    assert "PRIVATE_INPUT" not in str(error.value)


async def test_transport_timeout_is_retryable(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("private details", request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(grader.GradingError, match="in transit") as error:
        await grader.grade(snapshot())
    assert error.value.retryable


async def test_non_json_success_response_fails(monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(200, text="not JSON"))
    with pytest.raises(grader.GradingError, match="non-JSON"):
        await grader.grade(snapshot())
