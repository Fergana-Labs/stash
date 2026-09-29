"""Write a skill (SKILL.md) for an agent with GEPA, using a trained reward model as the metric.

    python -m rm_worker.gepa_run --job-dir DIR

Reads job.json and gepa_examples.jsonl; writes result.json
(see docs/reward-models/DESIGN.md, "Skill creation (GEPA)").
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

COMPONENT = "skill_body"

# GEPA fills in <curr_param> (the current skill body) and <side_info> (the examples with feedback).
REFLECTION_PROMPT_TEMPLATE = """You are writing the body of a SKILL.md for an AI agent. The agent loads the \
skill into its context and follows it when the skill's description applies. The skill's name and \
description are fixed; you only write the body.

Skill name: <skill_name>
Skill description: <skill_description>

The current body of the skill:
```
<curr_param>
```

Below are conversations the agent handled with this skill loaded, the agent's reply to each, and \
feedback on the reply: a score from a reward model trained on human ratings (0 to 1, higher is \
better) and the comments human reviewers left on the original conversation:
```
<side_info>
```

Write a new body for the skill. Draw concrete, reusable instructions from the feedback: what the \
agent must always do, what it must never do, and the domain facts and procedures it needs. Write \
for any future conversation this skill applies to, not only these examples. Use Markdown.

Return only the body inside a single ``` block, with no YAML frontmatter, no name and no description."""


def log(message: str) -> None:
    print(message, flush=True)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def render(messages: list[dict]) -> str:
    """Same "<role>: <content>" rendering the backend uses for training texts."""
    return "\n\n".join(f"{message['role']}: {message['content']}" for message in messages)


def render_skill(name: str, description: str, body: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


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
    """GEPAAdapter: run the task model with the candidate skill loaded, score the conversation with the reward model."""

    # None tells GEPA to propose new skill bodies with its own reflection_lm proposer.
    propose_new_texts = None

    def __init__(
        self,
        reward_model: RewardModel,
        reward_stats: dict,
        skill_name: str,
        skill_description: str,
        task_model: str,
        task_api_base: str | None,
    ):
        self.reward_model = reward_model
        self.reward_mean = reward_stats["mean"]
        self.reward_std = reward_stats["std"]
        self.skill_name = skill_name
        self.skill_description = skill_description
        self.completion_kwargs = {"model": task_model}
        if task_api_base is not None:
            self.completion_kwargs["api_base"] = task_api_base

    def system_message(self, example_system: str | None, skill_body: str) -> str:
        skill = render_skill(self.skill_name, self.skill_description, skill_body)
        skill_block = f'<skill name="{self.skill_name}">\n{skill}\n</skill>'
        if example_system is None:
            return skill_block
        return f"{example_system}\n\n{skill_block}"

    def reply(self, example: dict, skill_body: str) -> str:
        system = self.system_message(example["system"], skill_body)
        response = litellm.completion(
            messages=[{"role": "system", "content": system}] + example["messages"],
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
                reply = self.reply(example, candidate[COMPONENT])
            except litellm.BadRequestError as error:
                trajectories.append(
                    {"example": example, "reply": None, "error": str(error), "score": 0.0}
                )
                continue
            trajectories.append({"example": example, "reply": reply, "error": None, "score": None})

        succeeded = [t for t in trajectories if t["error"] is None]
        # The reward model never sees system steps (in training, scoring or here), so GEPA
        # cannot raise the score by writing things the reward model likes into the skill itself.
        texts = [
            render(t["example"]["messages"] + [{"role": "assistant", "content": t["reply"]}])
            for t in succeeded
        ]
        for trajectory, reward in zip(succeeded, self.reward_model.score(texts), strict=True):
            # Raw rewards saturate the sigmoid and leave GEPA no headroom, so standardize first.
            trajectory["score"] = sigmoid((reward - self.reward_mean) / self.reward_std)

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


def load_reward_stats(model_dir: Path) -> dict:
    stats_path = model_dir / "reward_stats.json"
    if not stats_path.exists():
        raise FileNotFoundError(
            f"{stats_path} is missing: this reward model was trained before reward calibration "
            "was added. Retrain it before using it for skill creation."
        )
    return json.loads(stats_path.read_text())


def run(job_dir: Path) -> dict:
    job = json.loads((job_dir / "job.json").read_text())
    examples = read_jsonl(job_dir / "gepa_examples.jsonl")
    if not examples:
        raise ValueError("gepa_examples.jsonl has no examples")
    for example in examples:
        if not example["messages"]:
            raise ValueError(f"example for trace {example['trace_id']} has no input messages")

    skill_name = job["skill_name"]
    skill_description = job["skill_description"]

    log(f"loading reward model from {job['reward_model_dir']}")
    adapter = RewardModelAdapter(
        RewardModel(job["reward_model_dir"]),
        reward_stats=load_reward_stats(Path(job["reward_model_dir"])),
        skill_name=skill_name,
        skill_description=skill_description,
        task_model=job["task_model"],
        task_api_base=job["task_api_base"],
    )
    log(f"optimizing over {len(examples)} examples, max_metric_calls={job['max_metric_calls']}")
    reflection_lm = RecordingReflectionLM(job["reflection_model"])
    # Annotated traces are few, so the same examples serve as trainset and valset: GEPA
    # reflects on minibatches of them and ranks candidates by the mean score over all of them.
    reflection_prompt = REFLECTION_PROMPT_TEMPLATE.replace("<skill_name>", skill_name).replace(
        "<skill_description>", skill_description
    )
    result = gepa.optimize(
        seed_candidate={COMPONENT: skill_description},
        trainset=examples,
        valset=examples,
        adapter=adapter,
        reflection_lm=reflection_lm,
        reflection_prompt_template=reflection_prompt,
        max_metric_calls=job["max_metric_calls"],
    )

    if reflection_lm.errors:
        raise RuntimeError(
            f"{len(reflection_lm.errors)} reflection model call(s) failed; the first one's traceback is printed above this error"
        ) from reflection_lm.errors[0]
    if len(result.candidates) == 1 and reflection_lm.successful_calls == 0:
        raise RuntimeError(
            "GEPA never proposed a new skill body: the reflection model was never called. "
            "Either max_metric_calls is too small to get past evaluating the seed skill, "
            "or building the reflection input failed (see the traceback above)."
        )

    def skill(candidate: dict[str, str]) -> str:
        return render_skill(skill_name, skill_description, candidate[COMPONENT])

    # GEPA puts the seed candidate at index 0.
    output = {
        "best_skill": skill(result.best_candidate),
        "best_score": result.val_aggregate_scores[result.best_idx],
        "seed_skill": skill(result.candidates[0]),
        "seed_score": result.val_aggregate_scores[0],
        "candidates": [
            {"skill": skill(candidate), "score": score}
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
        description="Write a skill for an agent with GEPA against a reward model."
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    run(parser.parse_args().job_dir)


if __name__ == "__main__":
    main()
