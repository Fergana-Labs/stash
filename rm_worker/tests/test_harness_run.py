"""No generated code runs locally: tests fake the remote Sandbox and provider."""

import json
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("modal")
from rm_worker import harness_run as harness


def observed_execution(task, **changes):
    rows = [
        {"index": index, **case["expected"], "input_mutated": False}
        for index, case in enumerate(task["cases"])
    ]
    return {
        "stdout": json.dumps({"observations": rows, "candidate_log": ""}),
        "stderr": "",
        "exit_code": 0,
        **changes,
    }


def test_verifier_uses_own_expectations_and_ignores_claimed_success():
    task = harness.TASKS["chunked"]
    assert harness.verifier(task, observed_execution(task))["passed"]
    assert not harness.verifier(
        task, {"stdout": '{"passed":true,"tests_passed":5}', "exit_code": 0}
    )["passed"]
    assert not harness.verifier(task, observed_execution(task, exit_code=124))["passed"]
    execution = observed_execution(task)
    payload = json.loads(execution["stdout"])
    payload["observations"][0]["value"] = [[True, 2], [3, 4], [5]]
    execution["stdout"] = json.dumps(payload)
    assert not harness.verifier(task, execution)["passed"]
    payload["observations"][0] = {"index": 0, **task["cases"][0]["expected"], "input_mutated": True}
    execution["stdout"] = json.dumps(payload)
    assert not harness.verifier(task, execution)["passed"]


def test_source_is_parsed_without_execution(monkeypatch):
    # This would raise or touch the filesystem if imported/executed, but it is
    # merely syntax-parsed here and will only run in an isolated cloud Sandbox.
    source = "raise RuntimeError('never execute locally')\ndef solve(values):\n    return values\n"
    assert harness.parse_artifact(json.dumps({"source": source})) == source
    for reply in ('{"passed":true}', "```python\npass\n```", '{"source":"def broken("}'):
        with pytest.raises((ValueError, SyntaxError)):
            harness.parse_artifact(reply)


@pytest.mark.parametrize("format", ["plain", "python_fence", "json", "json_fence"])
def test_realistic_provider_source_formats_are_parsed_as_inert_source(format):
    source = "def solve(values, size):\n    if size <= 0:\n        raise ValueError('size must be positive')\n    return [values[i:i+size] for i in range(0, len(values), size)]"
    replies = {
        "plain": source,
        "python_fence": "```python\n" + source + "\n```",
        "json": json.dumps({"source": source}),
        "json_fence": "```json\n" + json.dumps({"source": source}) + "\n```",
    }
    assert harness.parse_artifact(replies[format]) == source


@pytest.mark.parametrize(
    "reply",
    [
        "Here is the solution:\n```python\ndef solve(x): return x\n```",
        "The function works and all tests pass.",
        "```python\ndef solve(x): return x\n```\n```python\nprint('extra')\n```",
        '{"passed":true,"tests_passed":5}',
    ],
)
def test_artifact_rejects_prose_claims_and_multiple_blocks(reply):
    with pytest.raises((ValueError, SyntaxError)):
        harness.parse_artifact(reply)


def test_cloud_guard_prevents_local_generated_execution(monkeypatch, tmp_path):
    monkeypatch.delenv("RM_TRAINING_ON_CLOUD_GPU", raising=False)
    with pytest.raises(RuntimeError, match="cloud Modal Sandbox"):
        harness.execute_sandbox("def solve(x): return x", harness.TASKS["stable_unique"])
    with pytest.raises(RuntimeError, match="cloud Modal Sandbox"):
        harness.run(tmp_path)


def test_sandbox_has_no_secrets_network_mounts_or_hidden_answers(monkeypatch):
    monkeypatch.setenv("RM_TRAINING_ON_CLOUD_GPU", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-not-a-credential")
    task = harness.TASKS["stable_unique"]
    observed = observed_execution(task)
    written = {}
    created = {}
    commands = []
    ended = []

    class FakeFiles:
        def write_text(self, text, path):
            written[path] = text

        def read_text(self, path):
            return observed["stdout"] if path.endswith("stdout.log") else ""

    class FakeSandbox:
        object_id = "fake-only-no-cloud-launch"
        filesystem = FakeFiles()

        def exec(self, *args, **kwargs):
            commands.append((args, kwargs))
            return SimpleNamespace(wait=lambda: 0)

        def terminate(self):
            ended.append(True)

    def create(*args, **kwargs):
        created.update(kwargs)
        return FakeSandbox()

    monkeypatch.setattr(harness.modal.Sandbox, "create", create)
    result = harness.execute_sandbox("def solve(values): return values", task)
    assert created["block_network"] is True
    assert created["secrets"] == [] and created["env"] == {}
    assert created["volumes"] == {} and created["network_file_systems"] == {}
    assert created["include_oidc_identity_token"] is False
    assert created["memory"] == (256, 512)
    assert set(written) == {"/tmp/candidate.py", "/tmp/runner.py", "/tmp/inputs.json"}
    assert all(set(case) == {"args"} for case in json.loads(written["/tmp/inputs.json"]))
    assert "expected" not in written["/tmp/runner.py"]
    assert "env -i" in commands[0][0][2]
    assert commands[0][1]["secrets"] == []
    assert ended == [True]
    assert result["exit_code"] == 0
    assert harness.verifier(task, result)["passed"]


@pytest.mark.parametrize("provider_format", ["json", "plain", "python_fence"])
def test_paired_run_records_actual_checks_cost_and_scope(monkeypatch, tmp_path, provider_format):
    monkeypatch.setenv("RM_TRAINING_ON_CLOUD_GPU", "1")
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        source = "def solve(values, size):\n    return []\n"
        reply = {
            "json": json.dumps({"source": source}),
            "plain": source,
            "python_fence": "```python\n" + source + "```",
        }[provider_format]
        return SimpleNamespace(
            usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 20}),
            model="fixed-model-revision",
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
        )

    monkeypatch.setattr(harness, "complete", complete)
    monkeypatch.setattr(harness, "completion_cost", lambda response: 0.01)
    monkeypatch.setattr(
        harness, "execute_sandbox", lambda source, task, **kwargs: observed_execution(task)
    )
    (tmp_path / "job.json").write_text(
        json.dumps(
            {
                "kind": "harness",
                "task_ids": ["chunked", "rolling_sum"],
                "task_model": "same-model",
                "incumbent_skill": "baseline",
                "candidate_skill": "review edge cases",
            }
        )
    )
    result = harness.run(tmp_path)
    assert [row["arm"] for row in result["outcomes"]] == [
        "incumbent",
        "candidate",
        "candidate",
        "incumbent",
    ]
    assert len(calls) == 4 and {call["model"] for call in calls} == {"same-model"}
    assert {call["max_tokens"] for call in calls} == {2048}
    assert all(
        call["messages"][0]["content"].endswith("formatting instruction in the skill.")
        for call in calls
    )
    assert result["scope"] == harness.SCOPE
    assert result["metrics"]["completion_calls"] == 4
    assert result["metrics"]["provider_cost_usd_known"] == pytest.approx(0.04)
    assert result["metrics"]["paired_success_delta"] == 0
    assert result["metrics"]["prospective_agent_improvement_validated"] is False
    assert all(row["code_sha256"] == harness.digest(row["source"]) for row in result["outcomes"])
    assert json.loads((tmp_path / "result.json").read_text())["protocol"]["sandbox_network_blocked"]
    assert result["protocol"]["oracle_baseline"] is True
    assert result["metrics"]["optimization_metric"] == "oracle_test_success"
    assert result["metrics"]["adapter_uses_learned_reward"] is False
    assert "selection_uses_learned_reward" not in result["metrics"]


def test_learned_search_scores_stay_separate_from_independent_verification(monkeypatch, tmp_path):
    monkeypatch.setenv("RM_TRAINING_ON_CLOUD_GPU", "1")
    texts = []

    class FakeRewardModel:
        input_version = 1
        rubric = []

        def score(self, values):
            texts.extend(values)
            return [-4.0]

    provenance = {"model_key": "private/fixture", "feature_version": "v1", "manifest_digest": "m1"}
    monkeypatch.setattr(
        harness,
        "load_reward_model",
        lambda key, directory: (FakeRewardModel(), {"mean": 0.0, "std": 1.0}, provenance),
    )
    monkeypatch.setattr(
        harness,
        "complete",
        lambda **kwargs: SimpleNamespace(
            usage=None,
            model="same-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps({"source": "def solve(values):\n    return values\n"})
                    )
                )
            ],
        ),
    )
    monkeypatch.setattr(harness, "completion_cost", lambda response: 0.01)
    monkeypatch.setattr(
        harness, "execute_sandbox", lambda source, task, **kwargs: observed_execution(task)
    )
    # Stub only GEPA's result container; no policies or generated code execute.
    monkeypatch.setitem(
        sys.modules,
        "gepa",
        SimpleNamespace(EvaluationBatch=lambda **kwargs: SimpleNamespace(**kwargs)),
    )
    adapter = harness.HarnessAdapter(
        "same-model", reward_model_key="private/fixture", reward_cache_dir=tmp_path
    )
    result = adapter.evaluate(
        [{"task_id": "stable_unique"}],
        {"skill_body": "unique-secret-style-instructions"},
        capture_traces=True,
    )
    outcome = result.trajectories[0]
    assert outcome["verification"]["passed"] is True
    assert outcome["learned_reward"]["raw"] == -4
    assert result.scores == pytest.approx([harness.normalized_reward(-4, {"mean": 0, "std": 1})])
    assert result.scores[0] < 0.1
    assert outcome["optimization_metric"] == "learned_normalized_reward"
    assert "expected" not in texts[0] and "verification" not in texts[0]
    assert "unique-secret-style-instructions" not in texts[0]
    assert "captured_execution" in texts[0]
    feedback = adapter.make_reflective_dataset({}, result, ["skill_body"])["skill_body"][0][
        "Feedback"
    ]
    assert "Learned evaluator reward" in feedback
    assert "checks passed" not in feedback
    (tmp_path / "job.json").write_text(
        json.dumps(
            {
                "kind": "harness",
                "task_ids": ["stable_unique"],
                "task_model": "same-model",
                "incumbent_skill": "manual incumbent",
                "candidate_skill": "manual candidate",
                "reward_model_key": "private/fixture",
            }
        )
    )
    probe = harness.run(tmp_path)
    assert probe["metrics"]["adapter_uses_learned_reward"] is True
    assert probe["metrics"]["skill_selection_performed"] is False
    assert "selection_uses_learned_reward" not in probe["metrics"]


def test_reward_loading_is_cloud_only_before_download(monkeypatch, tmp_path):
    monkeypatch.delenv("RM_TRAINING_ON_CLOUD_GPU", raising=False)
    with pytest.raises(RuntimeError, match="cloud Modal Sandbox"):
        harness.load_reward_model("real/private/checkpoint", tmp_path)
    with pytest.raises(RuntimeError, match="cloud Modal Sandbox"):
        harness.HarnessAdapter(
            "same-model", reward_model_key="real/private/checkpoint", reward_cache_dir=tmp_path
        )
