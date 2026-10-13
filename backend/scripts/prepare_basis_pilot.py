"""Prepare a bounded public-human-label infrastructure pilot, without loading models.

This is not a customer-transfer or robustness benchmark. HelpSteer2 may have
appeared in foundation-model training; its validation split cannot establish
independent quality of the pretrained encoder.
"""

import argparse
import gzip
import hashlib
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

DATASET = "nvidia/HelpSteer2"
REVISION = "990b2711a36180dd19d9c94b8627844866f8982a"
CRITERIA = ("helpfulness", "correctness", "coherence")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def pairs_for(path: Path, partition: str, count: int, excluded: set[str], tokenizer) -> list[dict]:
    grouped = defaultdict(list)
    with gzip.open(path, "rt") as source:
        for line in source:
            row = json.loads(line)
            grouped[row["prompt"]].append(row)
    pairs = []
    for prompt, responses in sorted(grouped.items(), key=lambda item: digest(item[0])):
        group = digest(prompt)
        if group in excluded or len(responses) < 2:
            continue
        for criterion in CRITERIA:
            ordered = sorted(responses, key=lambda row: row[criterion])
            rejected, chosen = ordered[0], ordered[-1]
            if (
                chosen[criterion] <= rejected[criterion]
                or chosen["response"] == rejected["response"]
            ):
                continue

            def rendered(response):
                return tokenizer.apply_chat_template(
                    [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response},
                    ],
                    tokenize=False,
                    add_generation_prompt=False,
                )

            chosen_text = rendered(chosen["response"])
            rejected_text = rendered(rejected["response"])
            pairs.append(
                {
                    "example_id": digest(group + criterion + chosen_text + rejected_text),
                    "task_group": group,
                    "partition": partition,
                    "profile_id": "human_rating_criterion:" + criterion,
                    "domain": "general_response_quality",
                    "workflow_id": "helpsteer2_response_rating",
                    "agent": "public_dataset_response",
                    "action_type": "response",
                    "granularity": "action",
                    "chosen": chosen_text,
                    "rejected": rejected_text,
                    "provenance": {
                        "source": "human",
                        "dataset": DATASET,
                        "revision": REVISION,
                        "license": "CC-BY-4.0",
                        "criterion": criterion,
                        "chosen_rating": chosen[criterion],
                        "rejected_rating": rejected[criterion],
                        "independent_customer_identity": False,
                    },
                }
            )
            if len(pairs) >= count:
                return pairs
    return pairs


def prepare(directory: Path, base_model: str, train_count: int, eval_count: int) -> dict:
    if not 2 <= train_count <= 1000 or not 1 <= eval_count <= 500:
        raise ValueError("Pilot sizes exceed the bounded infrastructure run")
    directory.mkdir(parents=True, exist_ok=True)
    metadata = json.load(urllib.request.urlopen("https://huggingface.co/api/models/" + base_model))
    # Only small tokenizer files are downloaded here, never model weights.
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=metadata["sha"])
    for split in ("train", "validation"):
        target = directory / (split + ".jsonl.gz")
        if not target.exists():
            urllib.request.urlretrieve(
                f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{split}.jsonl.gz",
                target,
            )
    train = pairs_for(directory / "train.jsonl.gz", "train", train_count, set(), tokenizer)
    test = pairs_for(
        directory / "validation.jsonl.gz",
        "eval",
        eval_count,
        {row["task_group"] for row in train},
        tokenizer,
    )
    if len(train) != train_count or len(test) != eval_count:
        raise ValueError("Public dataset did not supply the requested pilot comparisons")
    job = {
        "kind": "basis_train",
        "base_model": base_model,
        "base_model_revision": metadata["sha"],
        "base_model_license": "Apache-2.0",
        "artifact_key": "reward-models/research/basis-pilot-"
        + digest(json.dumps(train + test))[:16]
        + ".tar.gz",
        "fixed_split": True,
        "input_version": 2,
        "input_serialization": "skywork_official_chat_template",
        "basis_options": {
            "basis_dimension": 4,
            "fit_steps": 200,
            "max_length": 1024,
            "batch_size": 2,
            "seed": 0,
            "l2": 0.05,
        },
        "research_scope": "public_human_label_infrastructure_pilot",
    }
    for name, value in (
        ("job.json", job),
        (
            "dataset_manifest.json",
            {
                "dataset": DATASET,
                "revision": REVISION,
                "license": "CC-BY-4.0",
                "attribution": "NVIDIA HelpSteer2 human annotation dataset",
                "source_url": f"https://huggingface.co/datasets/{DATASET}/tree/{REVISION}",
                "train_pairs": len(train),
                "evaluation_pairs": len(test),
                "customer_generalization_tested": False,
                "robustness_tested": False,
                "foundation_training_exposure": "unknown; no independent foundation-quality claim",
            },
        ),
    ):
        (directory / name).write_text(json.dumps(value, indent=2) + "\n")
    (directory / "pairs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in train + test))
    for name in ("score_items.jsonl", "action_score_items.jsonl"):
        (directory / name).write_text("")
    return {
        "base_model": base_model,
        "base_revision": metadata["sha"],
        "artifact_key": job["artifact_key"],
        "train_pairs": len(train),
        "evaluation_pairs": len(test),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument(
        "--base-model",
        choices=[
            "Skywork/Skywork-Reward-V2-Qwen3-0.6B",
            "Skywork/Skywork-Reward-V2-Qwen3-1.7B",
            "Skywork/Skywork-Reward-V2-Qwen3-4B",
        ],
        default="Skywork/Skywork-Reward-V2-Qwen3-0.6B",
    )
    parser.add_argument("--train-pairs", type=int, default=128)
    parser.add_argument("--eval-pairs", type=int, default=64)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(args.job_dir, args.base_model, args.train_pairs, args.eval_pairs), indent=2
        )
    )
