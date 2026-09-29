"""Optimize a system prompt with GEPA, using a trained reward model as the metric.

    python -m rm_worker.gepa_run --job-dir DIR

Reads job.json and gepa_examples.jsonl; writes result.json
(see docs/reward-models/DESIGN.md, "GEPA prompt optimization").
"""

import argparse
import json
import math
import sys
from pathlib import Path

import gepa
import litellm
from gepa import EvaluationBatch
from gepa.lm import LM

from rm_worker.scoring import RewardModel

COMPONENT = "system_prompt"


def log(message: str) -> None:
    print(message, flush=True)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def render(messages: list[dict]) -> str:
    """Same "<role>: <content>" rendering the backend uses for training texts."""
    return "\n\n".join(f"{message['role']}: {message['content']}" for message in messages)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class RecordingReflectionLM:
    """The reflection model, with every failed call recorded before it is re-raised.

    GEPA catches reflection errors, logs them and carries on, so a run whose
    reflection model is broken would otherwise finish like a run that found
    nothing better than the seed.
    """

    def __init__(self, model: str):
        self.lm = LM(model)
        self.errors: list[Exception] = []
        self.successful_calls = 0

    def __call__(self, prompt):
        try:
            output = self.lm(prompt)
        except Exception as error:
            self.errors.append(error)
            raise
        self.successful_calls += 1
        return output

    def batch_complete(self, messages_list, **kwargs):
        try:
            outputs = self.lm.batch_complete(messages_list, **kwargs)
        except Exception as error:
            self.errors.append(error)
            raise
        self.successful_calls += 1
        return outputs


class RewardModelAdapter:
    """GEPAAdapter: run the task model with the candidate prompt, score the conversation with the reward model."""

    # None tells GEPA to propose new prompts with its own reflection_lm proposer.
    propose_new_texts = None

    def __init__(self, reward_model: RewardModel, task_model: str, task_api_base: str | None):
        self.reward_model = reward_model
        self.completion_kwargs = {"model": task_model}
        if task_api_base is not None:
            self.completion_kwargs["api_base"] = task_api_base

    def reply(self, system_prompt: str, messages: list[dict]) -> str:
        response = litellm.completion(
            messages=[{"role": "system", "content": system_prompt}] + messages,
            **self.completion_kwargs,
        )
        return response.choices[0].message.content

    def evaluate(
        self, batch: list[dict], candidate: dict[str, str], capture_traces: bool = False
    ) -> EvaluationBatch:
        trajectories = []
        for example in batch:
            # GEPA's adapter contract: a per-example failure scores 0 and carries its error into
            # reflection instead of raising. Only the request being rejected counts as per-example;
            # auth, rate-limit and connection errors are systemic and still raise.
            try:
                reply = self.reply(candidate[COMPONENT], example["messages"])
            except litellm.BadRequestError as error:
                trajectories.append(
                    {"example": example, "reply": None, "error": str(error), "score": 0.0}
                )
                continue
            trajectories.append({"example": example, "reply": reply, "error": None, "score": None})

        succeeded = [t for t in trajectories if t["error"] is None]
        # The reward model never sees system steps (in training, scoring or here), so GEPA
        # cannot raise the score by writing things the reward model likes into the prompt itself.
        texts = [
            render(t["example"]["messages"] + [{"role": "assistant", "content": t["reply"]}])
            for t in succeeded
        ]
        for trajectory, reward in zip(succeeded, self.reward_model.score(texts), strict=True):
            trajectory["score"] = sigmoid(reward)

        return EvaluationBatch(
            outputs=[t["reply"] for t in trajectories],
            scores=[t["score"] for t in trajectories],
            trajectories=trajectories if capture_traces else None,
        )

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict]]:
        records = []
        for trajectory in eval_batch.trajectories:
            feedback = [f"Reward model score: {trajectory['score']:.3f} (0 to 1, higher is better)"]
            if trajectory["error"] is not None:
                feedback.append(f"The task model request failed: {trajectory['error']}")
            feedback += [
                f"Human reviewer comment: {comment}"
                for comment in trajectory["example"]["feedback"]
            ]
            records.append(
                {
                    "Inputs": {"conversation": render(trajectory["example"]["messages"])},
                    "Generated Outputs": trajectory["reply"] or "",
                    "Feedback": "\n".join(feedback),
                }
            )
        return {component: records for component in components_to_update}


def run(job_dir: Path) -> dict:
    job = json.loads((job_dir / "job.json").read_text())
    examples = read_jsonl(job_dir / "gepa_examples.jsonl")
    if not examples:
        raise ValueError("gepa_examples.jsonl has no examples")
    for example in examples:
        if not example["messages"]:
            raise ValueError(f"example for trace {example['trace_id']} has no input messages")

    log(f"loading reward model from {job['reward_model_dir']}")
    adapter = RewardModelAdapter(
        RewardModel(job["reward_model_dir"]),
        task_model=job["task_model"],
        task_api_base=job["task_api_base"],
    )
    log(f"optimizing over {len(examples)} examples, max_metric_calls={job['max_metric_calls']}")
    reflection_lm = RecordingReflectionLM(job["reflection_model"])
    # Annotated traces are few, so the same examples serve as trainset and valset: GEPA
    # reflects on minibatches of them and ranks candidates by the mean score over all of them.
    result = gepa.optimize(
        seed_candidate={COMPONENT: job["seed_prompt"]},
        trainset=examples,
        valset=examples,
        adapter=adapter,
        reflection_lm=reflection_lm,
        max_metric_calls=job["max_metric_calls"],
    )

    if reflection_lm.errors:
        raise RuntimeError(
            f"{len(reflection_lm.errors)} reflection model call(s) failed; the first one's traceback is printed above this error"
        ) from reflection_lm.errors[0]
    if len(result.candidates) == 1 and reflection_lm.successful_calls == 0:
        raise RuntimeError(
            "GEPA never proposed a new prompt: the reflection model was never called. "
            "Either max_metric_calls is too small to get past evaluating the seed prompt, "
            "or building the reflection input failed (see the traceback above)."
        )

    # GEPA puts the seed candidate at index 0.
    output = {
        "best_prompt": result.best_candidate[COMPONENT],
        "best_score": result.val_aggregate_scores[result.best_idx],
        "seed_score": result.val_aggregate_scores[0],
        "candidates": [
            {"prompt": candidate[COMPONENT], "score": score}
            for candidate, score in zip(result.candidates, result.val_aggregate_scores, strict=True)
        ],
    }
    (job_dir / "result.json").write_text(json.dumps(output, indent=2))
    log(
        f"done: seed_score={output['seed_score']:.3f} best_score={output['best_score']:.3f} candidates={len(output['candidates'])}"
    )
    return output


def main() -> None:
    # GEPA prints progress without flushing; line buffering keeps stdout and stderr in
    # order in worker.log, so the error that failed the job is the last thing in it.
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(
        description="Optimize a system prompt with GEPA against a reward model."
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)


if __name__ == "__main__":
    main()
