"""Train a Bradley–Terry reward model from a job directory.

    python -m rm_worker.train --job-dir DIR

Reads job.json, pairs.jsonl and score_items.jsonl; writes model/, scores.jsonl
and result.json (see docs/reward-models/DESIGN.md, "Job directory contract").
"""

import argparse
import json
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification

from rm_worker.artifacts import upload_model
from rm_worker.evaluation import action_score_rows, reward_stats, split_pairs
from rm_worker.scoring import load_tokenizer, pick_device, score_texts, tokenize

MAX_LENGTH = 1024
LEARNING_RATE = 1e-5
BATCH_SIZE = 4


def log(message: str) -> None:
    print(message, flush=True)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def write_reward_stats(model_dir: Path, scores: list[float]) -> None:
    """Mean and population std of preference-response rewards, for GEPA calibration."""
    stats = reward_stats(scores)
    (model_dir / "reward_stats.json").write_text(json.dumps(stats))
    log(f"reward stats: {json.dumps(stats)}")


def pair_rewards(model, tokenizer, batch: list[dict], device) -> tuple[torch.Tensor, torch.Tensor]:
    # Chosen and rejected go through one forward pass; the first half of the rewards is chosen.
    texts = [pair["chosen"] for pair in batch] + [pair["rejected"] for pair in batch]
    rewards = model(**tokenize(tokenizer, texts, device)).logits.squeeze(-1)
    return rewards[: len(batch)], rewards[len(batch) :]


@torch.no_grad()
def pairwise_accuracy(model, tokenizer, pairs: list[dict], device) -> float | None:
    if not pairs:
        return None
    model.eval()
    correct = 0
    for start in range(0, len(pairs), BATCH_SIZE):
        chosen, rejected = pair_rewards(model, tokenizer, pairs[start : start + BATCH_SIZE], device)
        correct += int((chosen > rejected).sum().item())
    return correct / len(pairs)


def train(job_dir: Path) -> dict:
    started = time.monotonic()
    job = json.loads((job_dir / "job.json").read_text())
    base_model = job["base_model"]
    epochs = job["epochs"]

    pairs = read_jsonl(job_dir / "pairs.jsonl")
    train_pairs, eval_pairs = split_pairs(pairs)
    score_items = read_jsonl(job_dir / "score_items.jsonl")
    device = pick_device()
    log(
        f"base_model={base_model} device={device} train_pairs={len(train_pairs)} eval_pairs={len(eval_pairs)}"
    )

    tokenizer = load_tokenizer(base_model, MAX_LENGTH)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model, num_labels=1, dtype=torch.float32
    )
    model.config.pad_token_id = tokenizer.pad_token_id
    model.config.use_cache = False
    # Long trace pairs otherwise retain every layer's activations for both responses.
    model.gradient_checkpointing_enable()
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    shuffler = random.Random(0)
    final_loss = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffler.shuffle(train_pairs)
        epoch_losses: list[float] = []
        for start in range(0, len(train_pairs), BATCH_SIZE):
            chosen, rejected = pair_rewards(
                model, tokenizer, train_pairs[start : start + BATCH_SIZE], device
            )
            loss = -F.logsigmoid(chosen - rejected).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_losses.append(loss.item())
            log(f"epoch {epoch}/{epochs} step {len(epoch_losses)} loss {loss.item():.4f}")
        final_loss = sum(epoch_losses) / len(epoch_losses)
        log(f"epoch {epoch}/{epochs} mean loss {final_loss:.4f}")

    eval_accuracy = pairwise_accuracy(model, tokenizer, eval_pairs, device)
    log(f"eval accuracy {eval_accuracy} on {len(eval_pairs)} trace-disjoint held-out pairs")

    model.save_pretrained(job_dir / "model")
    tokenizer.save_pretrained(job_dir / "model")

    scores = score_texts(
        model, tokenizer, [item["text"] for item in score_items], device, BATCH_SIZE
    )
    write_jsonl(
        job_dir / "scores.jsonl",
        [
            {"trace_id": item["trace_id"], "score": score}
            for item, score in zip(score_items, scores, strict=True)
        ],
    )
    log(f"scored {len(scores)} traces")
    calibration_texts = [pair[key] for pair in train_pairs for key in ("chosen", "rejected")]
    calibration_scores = score_texts(model, tokenizer, calibration_texts, device, BATCH_SIZE)
    write_reward_stats(job_dir / "model", calibration_scores)
    action_train = [p for p in train_pairs if p.get("granularity") == "action"]
    action_eval = [p for p in eval_pairs if p.get("granularity") == "action"]
    tool_eval = [p for p in action_eval if p.get("action_type") == "tool_call"]
    action_scores = []
    if action_train:
        reference = score_texts(
            model,
            tokenizer,
            [p[key] for p in action_train for key in ("chosen", "rejected")],
            device,
            BATCH_SIZE,
        )
        stats = reward_stats(reference)
        (job_dir / "model" / "action_reward_stats.json").write_text(json.dumps(stats))
        action_items = read_jsonl(job_dir / "action_score_items.jsonl")
        action_scores = action_score_rows(
            action_items,
            score_texts(
                model, tokenizer, [item["text"] for item in action_items], device, BATCH_SIZE
            ),
            stats,
        )
    write_jsonl(job_dir / "action_scores.jsonl", action_scores)
    upload_model(job_dir / "model", job["artifact_key"])

    result = {
        "metrics": {
            "train_pairs": len(train_pairs),
            "eval_pairs": len(eval_pairs),
            "eval_accuracy": eval_accuracy,
            "eval_split": "trace",
            "excluded_cross_trace_pairs": len(pairs) - len(train_pairs) - len(eval_pairs),
            "action_scoring_version": 1 if action_train else None,
            "action_train_pairs": len(action_train),
            "action_eval_pairs": len(action_eval),
            "action_eval_accuracy": pairwise_accuracy(model, tokenizer, action_eval, device),
            "tool_eval_pairs": len(tool_eval),
            "tool_eval_accuracy": pairwise_accuracy(model, tokenizer, tool_eval, device),
            # Mean Bradley–Terry loss over the last epoch's training batches.
            "final_loss": final_loss,
            "epochs": epochs,
            "device": str(device),
            "seconds": round(time.monotonic() - started, 1),
        }
    }
    (job_dir / "result.json").write_text(json.dumps(result, indent=2))
    log(f"done: {json.dumps(result['metrics'])}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a reward model from a job directory.")
    parser.add_argument("--job-dir", type=Path, required=True)
    train(parser.parse_args().job_dir)


if __name__ == "__main__":
    main()
