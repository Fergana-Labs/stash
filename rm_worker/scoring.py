"""Load a trained reward model and score texts with it."""

from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from rm_worker.context import encode_action_input


def pick_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_tokenizer(
    name_or_dir: str | Path,
    max_length: int | None = None,
    input_version: int | None = None,
    rubric: list[str] | None = None,
):
    # The end of a conversation is the part being judged, so long texts lose their beginning.
    kwargs = {"truncation_side": "left"}
    if max_length is not None:
        # Saved into tokenizer_config.json, so scoring truncates exactly like training did.
        kwargs["model_max_length"] = max_length
    if input_version is not None:
        kwargs["stash_input_version"] = input_version
    if rubric is not None:
        kwargs["stash_rubric"] = rubric
    tokenizer = AutoTokenizer.from_pretrained(name_or_dir, **kwargs)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def tokenize(tokenizer, texts: list[str], device: torch.device) -> dict[str, torch.Tensor]:
    if tokenizer.init_kwargs.get("stash_input_version") == 3:
        batch = tokenizer.pad(
            [{"input_ids": encode_action_input(tokenizer, text)} for text in texts],
            padding=True,
            return_tensors="pt",
        )
        return {key: value.to(device) for key, value in batch.items()}
    batch = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=tokenizer.model_max_length,
        return_tensors="pt",
    )
    return {key: value.to(device) for key, value in batch.items()}


@torch.no_grad()
def score_texts(
    model, tokenizer, texts: list[str], device: torch.device, batch_size: int
) -> list[float]:
    model.eval()
    if tokenizer.init_kwargs.get("stash_input_version") == 3:
        batch_size = min(batch_size, 2)
    scores: list[float] = []
    for start in range(0, len(texts), batch_size):
        batch = tokenize(tokenizer, texts[start : start + batch_size], device)
        rewards = model(**batch).logits.squeeze(-1)
        scores.extend(rewards.float().cpu().tolist())
    return scores


class RewardModel:
    """A saved reward model directory (as written by train.py), ready to score texts."""

    def __init__(self, model_dir: str | Path, batch_size: int = 4):
        self.device = pick_device()
        self.batch_size = batch_size
        self.tokenizer = load_tokenizer(model_dir)
        self.input_version = self.tokenizer.init_kwargs.get("stash_input_version", 1)
        self.rubric = self.tokenizer.init_kwargs.get("stash_rubric", [])
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device)

    def score(self, texts: list[str]) -> list[float]:
        return score_texts(self.model, self.tokenizer, texts, self.device, self.batch_size)
