"""Actual synthetic Python task execution in secretless, network-blocked sandboxes.

The trusted worker calls the task model and compares observed outputs with
registered hidden expectations. Generated Python only runs in a fresh Modal
Sandbox, never in this worker or on the laptop. No expected answers or verifier
implementation enter that sandbox. This pilot is not repository-agent evidence.

Modal isolation API verified against https://modal.com/docs/guide/sandbox-networking
and https://modal.com/docs/sdk/py/latest/Sandbox on 2026-10-12.
"""

import argparse
import ast
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import modal

SCOPE = "synthetic_owned_python_utilities_v1"
MAX_SOURCE_BYTES = 50_000
MAX_OUTPUT_BYTES = 131_072
MAX_TASKS = 10
SANDBOX_IMAGE = modal.Image.debian_slim(python_version="3.12")


def value_case(args, expected):
    return {"args": args, "expected": {"value": expected}}


def error_case(args, error_type):
    return {"args": args, "expected": {"error_type": error_type}}


# These are owned synthetic regression tasks. Inputs/expected results are
# authored independently of the task model and never loaded from model replies.
TASKS = {
    "chunked": {
        "spec": "Implement solve(values, size). Split the list into consecutive chunks of at most size, including the final short chunk. Empty input returns []. size must be a positive integer excluding bool; otherwise raise ValueError. Do not mutate the input.",
        "buggy_source": "def solve(values, size):\n    return [values[i:i+size] for i in range(0, len(values)-size+1, size)]\n",
        "cases": [
            value_case([[1, 2, 3, 4, 5], 2], [[1, 2], [3, 4], [5]]),
            value_case([[], 3], []),
            value_case([[7], 4], [[7]]),
            error_case([[1], 0], "ValueError"),
            error_case([[1], True], "ValueError"),
        ],
    },
    "stable_unique": {
        "spec": "Implement solve(values). Return distinct JSON values in their first occurrence order, using Python == for equality, including nested lists and dictionaries. Do not mutate the input.",
        "buggy_source": "def solve(values):\n    return list(set(values))\n",
        "cases": [
            value_case([[3, 1, 3, 2, 1]], [3, 1, 2]),
            value_case([[{"a": 1}, {"a": 1}, [1], [1], None]], [{"a": 1}, [1], None]),
            value_case([[]], []),
            value_case([[True, 1, False, 0, "1"]], [True, False, "1"]),
        ],
    },
    "merge_intervals": {
        "spec": "Implement solve(intervals). Each [start,end] is a closed numeric interval. Sort by start and merge overlaps or touching endpoints. Return new [start,end] lists, do not mutate input. Reject start>end with ValueError. Empty input returns [].",
        "buggy_source": "def solve(intervals):\n    output=[]\n    for start,end in intervals:\n        if output and start < output[-1][1]: output[-1][1]=end\n        else: output.append([start,end])\n    return output\n",
        "cases": [
            value_case([[[5, 8], [1, 4], [4, 6]]], [[1, 8]]),
            value_case([[[1, 10], [2, 3]]], [[1, 10]]),
            value_case([[[-5, -3], [-2, 0]]], [[-5, -3], [-2, 0]]),
            value_case([[]], []),
            error_case([[[4, 1]]], "ValueError"),
        ],
    },
    "rolling_sum": {
        "spec": "Implement solve(values, width). Return sums of each consecutive full window of width. Do not pad partial windows. width must be a positive integer excluding bool; otherwise ValueError. Return [] when width exceeds input length.",
        "buggy_source": "def solve(values, width):\n    return [sum(values[i:i+width]) for i in range(len(values))]\n",
        "cases": [
            value_case([[1, 2, 3, 4], 2], [3, 5, 7]),
            value_case([[-2, 0, 5], 1], [-2, 0, 5]),
            value_case([[1], 2], []),
            value_case([[], 1], []),
            error_case([[1], -1], "ValueError"),
            error_case([[1], True], "ValueError"),
        ],
    },
    "flatten_once": {
        "spec": "Implement solve(groups). groups must be a list of lists. Flatten exactly one level, preserving order and deeper nesting. Raise TypeError if any group is not a list. Do not mutate inputs.",
        "buggy_source": "def solve(groups):\n    return sum((list(group) for group in groups), [])\n",
        "cases": [
            value_case([[[1, 2], [], [3]]], [1, 2, 3]),
            value_case([[[[1]], [2]]], [[1], 2]),
            value_case([[]], []),
            error_case([["ab"]], "TypeError"),
            error_case([[[1], 3]], "TypeError"),
        ],
    },
    "parse_pairs": {
        "spec": "Implement solve(text). Parse comma-separated key=value entries. Trim whitespace around keys and values. Empty/whitespace input returns {}. Split each entry at its first '=' so values may contain '='. Empty keys, missing '=', and duplicate keys raise ValueError.",
        "buggy_source": "def solve(text):\n    return dict(part.split('=') for part in text.split(','))\n",
        "cases": [
            value_case([" a = 1 , b =x=y "], {"a": "1", "b": "x=y"}),
            value_case(["  "], {}),
            value_case(["x="], {"x": ""}),
            error_case(["a=1,a=2"], "ValueError"),
            error_case(["=1"], "ValueError"),
            error_case(["abc"], "ValueError"),
        ],
    },
    "coalesce_ranges": {
        "spec": "Implement solve(ranges). Merge half-open integer [start,end) ranges, including adjacent ranges. Sort input, reject reversed ranges with ValueError, drop zero-length ranges. Return new lists without mutating input.",
        "buggy_source": "def solve(ranges):\n    return sorted(ranges)\n",
        "cases": [
            value_case([[[3, 5], [1, 3], [9, 9]]], [[1, 5]]),
            value_case([[[1, 9], [2, 3], [10, 12]]], [[1, 9], [10, 12]]),
            value_case([[[0, 0]]], []),
            error_case([[[3, 2]]], "ValueError"),
            value_case([[[-3, -1], [-1, 0]]], [[-3, 0]]),
        ],
    },
    "paginate": {
        "spec": "Implement solve(values, page, page_size). Return the zero-based page. page must be a nonnegative integer and page_size a positive integer; neither accepts bool. Invalid parameters raise ValueError. Out-of-range pages return [].",
        "buggy_source": "def solve(values, page, page_size):\n    return values[page:page+page_size]\n",
        "cases": [
            value_case([[1, 2, 3, 4, 5], 1, 2], [3, 4]),
            value_case([[1, 2, 3], 1, 2], [3]),
            value_case([[1], 8, 2], []),
            error_case([[1], -1, 1], "ValueError"),
            error_case([[1], True, 1], "ValueError"),
            error_case([[1], 0, 0], "ValueError"),
        ],
    },
}


# This runner knows input cases but never expected answers. In particular,
# candidate code cannot monkeypatch an assertion to make the outside verifier
# report success. Claimed test results printed by candidate code are ignored.
RUNNER_SOURCE = r"""
import contextlib
import importlib.util
import io
import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_FSIZE, (131072, 131072))
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))

class BoundedLog(io.StringIO):
    def write(self, text):
        if self.tell() + len(text) > 8192:
            raise RuntimeError("Candidate output exceeds budget")
        return super().write(text)

with open("/tmp/inputs.json") as source:
    inputs = json.load(source)
log = BoundedLog()
observations = []
try:
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        spec = importlib.util.spec_from_file_location("candidate", "/tmp/candidate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for index, case in enumerate(inputs):
            try:
                original = json.dumps(case, sort_keys=True)
                value = module.solve(*case["args"])
                observations.append({"index": index, "value": value, "input_mutated": json.dumps(case, sort_keys=True) != original})
            except Exception as error:
                observations.append({"index": index, "error_type": type(error).__name__, "input_mutated": json.dumps(case, sort_keys=True) != original})
except Exception as error:
    observations = [{"load_error_type": type(error).__name__}]
print(json.dumps({"observations": observations, "candidate_log": log.getvalue()}, allow_nan=False))
"""


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def complete(**kwargs):
    import litellm

    return litellm.completion(**kwargs)


def completion_cost(response):
    import litellm

    return litellm.completion_cost(completion_response=response)


def require_cloud():
    if os.environ.get("RM_TRAINING_ON_CLOUD_GPU") != "1":
        raise RuntimeError("Generated-code harness execution must run in a cloud Modal Sandbox")


def load_reward_model(key: str, directory: Path):
    """Never download/load a substantive evaluator on the laptop."""
    require_cloud()
    from rm_worker.artifacts import download_model
    from rm_worker.scoring import RewardModel

    model_dir = download_model(key, directory)
    stats = json.loads((model_dir / "reward_stats.json").read_text())
    if (
        type(stats.get("mean")) not in (int, float)
        or type(stats.get("std")) not in (int, float)
        or not math.isfinite(stats["mean"])
        or not math.isfinite(stats["std"])
        or stats["std"] <= 0
    ):
        raise ValueError("Stored evaluator has an invalid normalization scale")
    model = RewardModel(model_dir)
    manifest = getattr(getattr(model, "basis", None), "manifest", {})
    provenance = {
        "model_key": key,
        "evaluator_kind": manifest.get("evaluator_kind", "scalar_reward"),
        "feature_version": manifest.get("feature_version"),
        "manifest_digest": manifest.get("manifest_digest"),
    }
    return model, stats, provenance


def normalized_reward(raw: float, stats: dict) -> float:
    if not math.isfinite(raw):
        raise ValueError("Evaluator returned a non-finite harness reward")
    # This display/search scale is not a probability of correctness.
    return 0.5 * (1 + math.tanh((raw - stats["mean"]) / (2 * stats["std"])))


def reward_input(task: dict, outcome: dict, model) -> str:
    """Judge captured evidence without revealing oracle labels or skill text."""
    artifact = {
        "source": outcome["source"],
        "code_sha256": outcome["code_sha256"],
        "artifact_error": outcome["artifact_error"],
        "captured_execution": {
            key: outcome["execution"].get(key)
            for key in ("exit_code", "stdout", "stderr", "sandbox_error")
        }
        if outcome["execution"] is not None
        else None,
    }
    messages = [
        {
            "role": "user",
            "content": "Task requirements:\n"
            + task["spec"]
            + "\n\nBuggy starting artifact:\n"
            + task["buggy_source"],
        },
        {
            "role": "assistant",
            "content": "Replacement artifact and captured execution evidence:\n"
            + json.dumps(artifact, sort_keys=True, allow_nan=False),
        },
    ]
    if getattr(model, "input_version", 1) == 3:
        from rm_worker.context import render_action_input

        return render_action_input(messages, model.rubric)
    return "\n\n".join(f"{message['role']}: {message['content']}" for message in messages)


def parse_artifact(reply: str) -> str:
    if not isinstance(reply, str) or len(reply.encode()) > MAX_SOURCE_BYTES + 10_000:
        raise ValueError("Task model artifact exceeds source budget")
    text = reply.strip()
    # Providers can return Python even when JSON mode was requested. Accept a
    # complete code block or plain source as inert text, never surrounding prose.
    # All accepted formats still go through AST validation and the same sandbox.
    if text.startswith("```"):
        fenced = re.fullmatch(r"```(?:python|py|json)?[ \t]*\n([\s\S]*?)\n?```", text)
        if fenced is None or "```" in fenced.group(1):
            raise ValueError("Artifact must contain exactly one complete source block")
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        source = text
    else:
        if not isinstance(payload, dict) or set(payload) != {"source"}:
            raise ValueError("Task model JSON must return exactly a source field")
        source = payload["source"]
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid generated source")
    # Parsing is safe; never compile, import, eval or exec this source here.
    module = ast.parse(source)
    if not any(isinstance(node, ast.FunctionDef) and node.name == "solve" for node in module.body):
        raise ValueError("Generated source must define solve")
    return source


def same_value(actual, expected):
    """Do not accept True as a replacement for the numeric result 1."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(same_value(a, b) for a, b in zip(actual, expected, strict=True))
        )
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(same_value(actual[key], expected[key]) for key in expected)
        )
    return type(actual) is type(expected) and actual == expected


def verifier(task: dict, execution: dict) -> dict:
    """Trusted expected values remain in the parent, outside candidate control."""
    observations = None
    protocol_error = None
    try:
        if len(execution["stdout"].encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("Output exceeds budget")
        payload = json.loads(execution["stdout"])
        observations = payload["observations"]
        if not isinstance(observations, list) or len(observations) != len(task["cases"]):
            raise ValueError("Wrong number of observed cases")
        if any(
            not isinstance(row, dict) or type(row.get("index")) is not int for row in observations
        ) or [row.get("index") for row in observations] != list(range(len(observations))):
            raise ValueError("Observed case identities differ")
    except (ValueError, KeyError, TypeError) as error:
        protocol_error = type(error).__name__
    checks = []
    for index, case in enumerate(task["cases"]):
        observed = observations[index] if protocol_error is None else {}
        expected = case["expected"]
        passed = (
            execution["exit_code"] == 0
            and protocol_error is None
            and observed.get("input_mutated") is False
        )
        if "error_type" in expected:
            passed = passed and observed.get("error_type") == expected["error_type"]
        else:
            passed = (
                passed and "value" in observed and same_value(observed["value"], expected["value"])
            )
        checks.append(
            {
                "case_index": index,
                "passed": bool(passed),
                "expected": expected,
                "observed": observed,
            }
        )
    return {
        "passed": all(row["passed"] for row in checks),
        "passed_cases": sum(row["passed"] for row in checks),
        "total_cases": len(checks),
        "checks": checks,
        "protocol_error": protocol_error,
    }


def execute_sandbox(source: str, task: dict, *, timeout: int = 30) -> dict:
    require_cloud()
    started = time.monotonic()
    # No inherited worker image, source mounts, secrets, volumes or OIDC token.
    # A Sandbox is not authorized for the parent's Modal resources by default.
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        image=SANDBOX_IMAGE,
        timeout=timeout,
        cpu=(1, 1),
        memory=(256, 512),
        secrets=[],
        volumes={},
        network_file_systems={},
        env={},
        block_network=True,
        include_oidc_identity_token=False,
    )
    output = {
        "sandbox_id": sandbox.object_id,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "sandbox_error": None,
    }
    try:
        sandbox.filesystem.write_text(source, "/tmp/candidate.py")
        sandbox.filesystem.write_text(RUNNER_SOURCE, "/tmp/runner.py")
        sandbox.filesystem.write_text(
            json.dumps([{"args": case["args"]} for case in task["cases"]]), "/tmp/inputs.json"
        )
        # The command is a fixed string, with no generated text interpolated.
        # env -i strips even sandbox metadata from the candidate process.
        process = sandbox.exec(
            "sh",
            "-c",
            "exec env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONHASHSEED=0 python -I -B /tmp/runner.py > /tmp/stdout.log 2>/tmp/stderr.log",
            timeout=min(timeout, 15),
            secrets=[],
        )
        output["exit_code"] = process.wait()
        for stream in ("stdout", "stderr"):
            value = sandbox.filesystem.read_text(f"/tmp/{stream}.log")
            if len(value.encode()) > MAX_OUTPUT_BYTES:
                raise ValueError("Sandbox output exceeds budget")
            output[stream] = value
    except Exception as error:
        # Record type only: systemic SDK/provider errors can contain credentials.
        output["sandbox_error"] = type(error).__name__
    finally:
        try:
            sandbox.terminate()
        except Exception as error:
            output["termination_error"] = type(error).__name__
    output["seconds"] = round(time.monotonic() - started, 4)
    output["isolation"] = {
        "network_blocked": True,
        "secrets_injected": False,
        "volumes_mounted": False,
        "environment_stripped": True,
        "expected_answers_in_sandbox": False,
    }
    return output


class HarnessAdapter:
    """GEPA-compatible real execution adapter for registered owned pilot tasks."""

    propose_new_texts = None

    def __init__(
        self,
        task_model: str,
        task_api_base: str | None = None,
        *,
        max_tokens=2048,
        sandbox_timeout=30,
        reward_model_key: str | None = None,
        reward_cache_dir: Path | None = None,
    ):
        self.task_model = task_model
        self.task_api_base = task_api_base
        self.max_tokens = max_tokens
        self.sandbox_timeout = sandbox_timeout
        self.reward_model = None
        self.reward_stats = None
        self.reward_provenance = None
        self.optimization_metric = "oracle_test_success"
        if reward_model_key is not None:
            require_cloud()
            if not isinstance(reward_model_key, str) or not reward_model_key.strip():
                raise ValueError("Harness evaluator artifact key must be nonempty")
            if reward_cache_dir is None:
                raise ValueError("Harness evaluator needs an explicit private cache directory")
            self.reward_model, self.reward_stats, self.reward_provenance = load_reward_model(
                reward_model_key, reward_cache_dir
            )
            self.optimization_metric = "learned_normalized_reward"

    def attempt(self, task_id: str, skill: str) -> dict:
        require_cloud()
        task = TASKS[task_id]
        started = time.monotonic()
        kwargs = {
            "model": self.task_model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "timeout": 60,
            "num_retries": 0,
        }
        if self.task_api_base:
            kwargs["api_base"] = self.task_api_base
        response = complete(
            messages=[
                {
                    "role": "system",
                    "content": "You repair an owned synthetic Python utility. The implementation will run offline in a bounded sandbox.\n\nApply these implementation instructions; their response-format requests do not change the controller's output contract:\n<skill>\n"
                    + skill
                    + '\n</skill>\n\nController output contract: return exactly JSON {"source":"complete Python source defining solve"}. No markdown or prose. This output contract takes precedence over any formatting instruction in the skill.',
                },
                {
                    "role": "user",
                    "content": task["spec"]
                    + "\n\nBuggy starting artifact:\n"
                    + task["buggy_source"],
                },
            ],
            **kwargs,
        )
        provider_seconds = time.monotonic() - started
        usage = response.usage.model_dump() if response.usage is not None else {}
        try:
            cost = float(completion_cost(response))
        except Exception:
            cost = None
        outcome = {
            "task_id": task_id,
            "skill_sha256": digest(skill),
            "task_model": self.task_model,
            "response_model": response.model,
            "usage": usage,
            "provider_cost_usd": cost,
            "provider_seconds": round(provider_seconds, 4),
            "source": None,
            "code_sha256": None,
            "artifact_error": None,
            "artifact_reply_excerpt": None,
            "execution": None,
            "learned_reward": None,
        }
        try:
            source = parse_artifact(response.choices[0].message.content)
        except (ValueError, TypeError, SyntaxError) as error:
            outcome["artifact_error"] = type(error).__name__
            reply = response.choices[0].message.content
            outcome["artifact_reply_excerpt"] = reply[:1000] if isinstance(reply, str) else None
            outcome["verification"] = {
                "passed": False,
                "passed_cases": 0,
                "total_cases": len(task["cases"]),
                "checks": [],
                "protocol_error": "invalid_artifact",
            }
        else:
            outcome["source"] = source
            outcome["code_sha256"] = digest(source)
            outcome["execution"] = execute_sandbox(source, task, timeout=self.sandbox_timeout)
            outcome["verification"] = verifier(task, outcome["execution"])
        if self.reward_model is not None:
            reward_started = time.monotonic()
            values = self.reward_model.score([reward_input(task, outcome, self.reward_model)])
            if len(values) != 1:
                raise ValueError("Evaluator returned the wrong number of harness scores")
            raw = float(values[0])
            outcome["learned_reward"] = {
                **self.reward_provenance,
                "raw": raw,
                "normalized": normalized_reward(raw, self.reward_stats),
                "normalization": self.reward_stats,
                "calibrated_success_probability": False,
                "seconds": round(time.monotonic() - reward_started, 4),
            }
        outcome["optimization_metric"] = self.optimization_metric
        outcome["seconds"] = round(time.monotonic() - started, 4)
        return outcome

    def evaluate(self, batch: list[dict], candidate: dict[str, str], capture_traces: bool = False):
        from gepa import EvaluationBatch

        outcomes = [self.attempt(example["task_id"], candidate["skill_body"]) for example in batch]
        return EvaluationBatch(
            outputs=[row["source"] for row in outcomes],
            scores=[
                row["learned_reward"]["normalized"]
                if self.reward_model is not None
                else float(row["verification"]["passed"])
                for row in outcomes
            ],
            trajectories=outcomes if capture_traces else None,
        )

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        # Keep hidden expected values out of candidate prompts. Tasks used for
        # reflection are development data, never later called untouched tests.
        records = [
            {
                "Inputs": {"task": TASKS[row["task_id"]]["spec"]},
                "Generated Outputs": row["source"] or "",
                "Feedback": (
                    f"Learned evaluator reward: {row['learned_reward']['normalized']:.4f}, an uncalibrated search score. Artifact error: {row['artifact_error']}."
                    if self.reward_model is not None
                    else f"Oracle baseline: independent execution checks passed {row['verification']['passed_cases']}/{row['verification']['total_cases']}. Artifact error: {row['artifact_error']}."
                ),
            }
            for row in eval_batch.trajectories
        ]
        return {component: records for component in components_to_update}


def run(job_dir: Path) -> dict:
    require_cloud()
    job = json.loads((job_dir / "job.json").read_text())
    if job.get("kind") != "harness":
        raise ValueError("Harness requires kind=harness")
    task_ids = job.get("task_ids", list(TASKS))
    if (
        not isinstance(task_ids, list)
        or not 1 <= len(task_ids) <= MAX_TASKS
        or len(set(task_ids)) != len(task_ids)
        or any(name not in TASKS for name in task_ids)
    ):
        raise ValueError("Harness needs a bounded unique list of registered owned tasks")
    for key in ("incumbent_skill", "candidate_skill", "task_model"):
        if not isinstance(job.get(key), str) or len(job[key]) > 20_000:
            raise ValueError(f"Invalid harness {key}")
    max_tokens = job.get("max_completion_tokens", 2048)
    sandbox_timeout = job.get("sandbox_timeout", 30)
    if (
        type(max_tokens) is not int
        or not 1 <= max_tokens <= 4096
        or type(sandbox_timeout) is not int
        or not 10 <= sandbox_timeout <= 30
    ):
        raise ValueError("Invalid harness completion or sandbox budget")
    adapter = HarnessAdapter(
        job["task_model"],
        job.get("task_api_base"),
        max_tokens=max_tokens,
        sandbox_timeout=sandbox_timeout,
        reward_model_key=job.get("reward_model_key"),
        reward_cache_dir=job_dir / "reward_checkpoint",
    )
    outcomes = []
    for index, task_id in enumerate(task_ids):
        # Alternate order to avoid making all incumbents systematically earlier.
        order = ("incumbent", "candidate") if index % 2 == 0 else ("candidate", "incumbent")
        for arm in order:
            outcome = adapter.attempt(task_id, job[f"{arm}_skill"])
            outcomes.append({**outcome, "arm": arm})
    counts = {
        arm: sum(row["verification"]["passed"] for row in outcomes if row["arm"] == arm)
        for arm in ("incumbent", "candidate")
    }
    output = {
        "scope": SCOPE,
        "outcomes": outcomes,
        "metrics": {
            "tasks": len(task_ids),
            "completion_calls": len(outcomes),
            "incumbent_passed": counts["incumbent"],
            "candidate_passed": counts["candidate"],
            "incumbent_success_rate": counts["incumbent"] / len(task_ids),
            "candidate_success_rate": counts["candidate"] / len(task_ids),
            "paired_success_delta": (counts["candidate"] - counts["incumbent"]) / len(task_ids),
            "provider_cost_usd_known": sum(row["provider_cost_usd"] or 0 for row in outcomes),
            "cost_unknown_calls": sum(row["provider_cost_usd"] is None for row in outcomes),
            "adapter_uses_learned_reward": adapter.reward_model is not None,
            "skill_selection_performed": False,
            "optimization_metric": adapter.optimization_metric,
            "incumbent_mean_learned_reward": sum(
                row["learned_reward"]["normalized"] for row in outcomes if row["arm"] == "incumbent"
            )
            / len(task_ids)
            if adapter.reward_model is not None
            else None,
            "candidate_mean_learned_reward": sum(
                row["learned_reward"]["normalized"] for row in outcomes if row["arm"] == "candidate"
            )
            / len(task_ids)
            if adapter.reward_model is not None
            else None,
            "repository_tasks": False,
            "prospective_agent_improvement_validated": False,
        },
        "protocol": {
            "same_task_model": job["task_model"],
            "same_completion_budget": max_tokens,
            "order": "alternating_paired",
            "verifier": "parent_compares_observed_outputs_to_registered_hidden_expectations",
            "task_suite_sha256": digest(json.dumps(TASKS, sort_keys=True)),
            "runner_sha256": digest(RUNNER_SOURCE),
            "sandbox_image": "debian_slim_python_3.12",
            "sandbox_network_blocked": True,
            "sandbox_secrets": False,
            "optimization_metric": adapter.optimization_metric,
            "reward_model": adapter.reward_provenance,
            "oracle_baseline": adapter.reward_model is None,
            "reward_input_includes_oracle_results": False,
        },
    }
    (job_dir / "result.json").write_text(json.dumps(output, indent=2, allow_nan=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Execute owned synthetic coding tasks in isolated Modal Sandboxes."
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)
