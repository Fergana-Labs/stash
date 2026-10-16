"""Qwen generation and reward-labeled DPO. Import ML packages only on Modal."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def require_cloud():
    if sys.platform == "darwin" or not os.getenv("MODAL_TASK_ID"):
        raise RuntimeError(
            "Qwen weights must never be loaded on the laptop; use the approved Modal job"
        )


def generate(model_spec, messages, seed, adapter=None):
    require_cloud()
    started = time.monotonic()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    key = (model_spec["id"], model_spec["revision"], adapter)
    # Container-local reuse, not a hidden change in model or checkpoint.
    if getattr(generate, "key", None) != key:
        if hasattr(generate, "model"):
            del generate.model
            torch.cuda.empty_cache()
        generate.tokenizer = AutoTokenizer.from_pretrained(
            model_spec["id"], revision=model_spec["revision"]
        )
        generate.model = AutoModelForCausalLM.from_pretrained(
            model_spec["id"],
            revision=model_spec["revision"],
            torch_dtype=torch.bfloat16,
            device_map={"": "cuda"},
            attn_implementation="sdpa",
        )
        if adapter:
            from peft import PeftModel

            adapter_path = Path("/checkpoints") / adapter
            if (
                not adapter_path.resolve().is_relative_to(Path("/checkpoints"))
                or not (adapter_path / "training.json").exists()
            ):
                raise ValueError("Unknown trained adapter")
            training = json.loads((adapter_path / "training.json").read_text())
            if training["model"] != model_spec or training["steps"] != training["requested_steps"]:
                raise ValueError("Adapter is incompatible or training did not finish")
            generate.model = PeftModel.from_pretrained(generate.model, str(adapter_path))
        generate.model.eval()
        generate.key = key
    tokenizer, model = generate.tokenizer, generate.model
    torch.manual_seed(seed)
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    encoded = tokenizer(prompt, return_tensors="pt").to(model.device)
    if encoded.input_ids.shape[1] > 6000:
        raise ValueError("Generation context exceeds the frozen budget")
    with torch.inference_mode():
        result = model.generate(
            **encoded,
            max_new_tokens=4096,
            do_sample=True,
            temperature=0.7,
            top_p=0.8,
            top_k=20,
            pad_token_id=tokenizer.eos_token_id,
        )
    tail = result[0, encoded.input_ids.shape[1] :]
    return {
        "text": tokenizer.decode(tail, skip_special_tokens=True),
        "model": model_spec,
        "seed": seed,
        "adapter": adapter,
        "usage": {"input_tokens": encoded.input_ids.shape[1], "output_tokens": tail.shape[0]},
        "finish_reason": "length" if tail.shape[0] >= 4096 else "stop",
        "gpu_function_seconds": time.monotonic() - started,
    }


def train_dpo(model_spec, pairs, config, run_id):
    require_cloud()
    from .corpus import digest

    if config.get("pairs_sha256") != digest(json.dumps(pairs, sort_keys=True)) or any(
        pair.get("reward") != config.get("reward") for pair in pairs
    ):
        raise ValueError("Training pair contents or frozen reward identity changed")
    if not 1 <= config["dpo_steps"] <= 40:
        raise ValueError("This pilot permits at most 40 training steps")
    if not run_id or len(run_id) > 64 or any(c not in "0123456789abcdef-" for c in run_id):
        raise ValueError("Invalid training run id")
    directory = Path("/checkpoints") / run_id
    previous = directory / "training.json"
    if previous.exists():
        record = json.loads(previous.read_text())
        if (
            record["experiment"] != config["sha256"]
            or record["model"] != model_spec
            or record.get("reward") != config.get("reward")
            or record.get("pairs_sha256") != config["pairs_sha256"]
        ):
            raise ValueError("Checkpoint belongs to a different experiment")
        return record
    import torch
    import torch.nn.functional as F
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .protocol import SYSTEM

    if len(pairs) < 4 or any(p["partition"] != "train" for p in pairs):
        raise ValueError(
            "DPO needs four independent training tasks and must never see dev/test data"
        )
    tokenizer = AutoTokenizer.from_pretrained(model_spec["id"], revision=model_spec["revision"])
    model = AutoModelForCausalLM.from_pretrained(
        model_spec["id"],
        revision=model_spec["revision"],
        torch_dtype=torch.bfloat16,
        device_map={"": "cuda"},
        attn_implementation="sdpa",
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            task_type="CAUSAL_LM",
        ),
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-5)
    torch.manual_seed(config["seed"])

    def encode(pair, response):
        messages = [
            {"role": "system", "content": SYSTEM + "\n\n" + pair["instructions"]},
            {"role": "user", "content": pair["brief"]},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        prefix = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        # Concatenation preserves the exact prefix boundary used to mask the loss.
        suffix = tokenizer(response, add_special_tokens=False)["input_ids"] + [
            tokenizer.eos_token_id
        ]
        ids = torch.tensor([prefix + suffix], device="cuda")
        if ids.shape[1] > 6144:
            raise ValueError("DPO example exceeds context budget; never truncate a design silently")
        return ids, len(prefix)

    encoded_pairs = [(encode(p, p["chosen"]), encode(p, p["rejected"])) for p in pairs]

    def logp(encoded):
        ids, prefix = encoded
        logits = model(input_ids=ids).logits[:, :-1, :]
        losses = F.cross_entropy(
            logits.reshape(-1, logits.shape[-1]).float(), ids[:, 1:].reshape(-1), reduction="none"
        )
        return -losses[prefix - 1 :].sum()

    # Cache reference log-probabilities with adapters disabled; no second model copy.
    model.eval()
    references = []
    with torch.no_grad(), model.disable_adapter():
        for chosen, rejected in encoded_pairs:
            references.append((logp(chosen) - logp(rejected)).item())
    model.train()
    started, losses, completed = time.monotonic(), [], 0
    for step in range(config["dpo_steps"]):
        if time.monotonic() - started > 30 * 60:
            break
        index = step % len(encoded_pairs)
        chosen, rejected = encoded_pairs[index]
        optimizer.zero_grad(set_to_none=True)
        margin = logp(chosen) - logp(rejected) - references[index]
        loss = -F.logsigmoid(config["dpo_beta"] * margin)
        if not torch.isfinite(loss):
            raise ValueError("DPO produced a non-finite loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        completed += 1
        losses.append(float(loss.detach()))
    directory.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(directory)
    tokenizer.save_pretrained(directory)
    record = {
        "model": model_spec,
        "method": "reward-labeled DPO LoRA",
        "rank": 8,
        "steps": completed,
        "requested_steps": config["dpo_steps"],
        "pairs": len(pairs),
        "losses": losses,
        "elapsed_seconds": time.monotonic() - started,
        "adapter": run_id,
        "label_source": "frozen_classifier",
        "human_labeled": False,
        "partition": "train",
        "experiment": config["sha256"],
        "reward": config.get("reward"),
        "pairs_sha256": config["pairs_sha256"],
    }
    (directory / "training.json").write_text(json.dumps(record, indent=2))
    return record
