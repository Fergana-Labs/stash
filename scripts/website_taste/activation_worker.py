"""Frozen multimodal forward pass, restricted to cloud workers. No generation."""

from __future__ import annotations

import base64
import io
import json
import time

from .activation_spec import SPEC, model_text
from .cloud_worker import require_cloud
from .corpus import digest


def extract(payloads, spec):
    require_cloud()  # Before importing model libraries or opening any weights.
    if spec != SPEC or not 1 <= len(payloads) <= 32:
        raise ValueError("Unknown representation or batch exceeds pilot cap")
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    started = time.monotonic()
    if not hasattr(extract, "model"):
        extract.processor = AutoProcessor.from_pretrained(
            SPEC["model"],
            revision=SPEC["revision"],
            min_pixels=SPEC["min_pixels"],
            max_pixels=SPEC["max_pixels"],
            use_fast=False,
        )
        extract.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            SPEC["model"],
            revision=SPEC["revision"],
            torch_dtype=torch.bfloat16,
            device_map={"": "cuda"},
            attn_implementation="sdpa",
        )
        extract.model.requires_grad_(False)
        extract.model.eval()
    model, processor = extract.model, extract.processor
    results = []
    for payload in payloads:
        if time.monotonic() - started > 12 * 60:
            raise ValueError("Activation extraction reached the bounded pilot time")
        data = payload["input"]
        raw = base64.b64decode(payload["image_base64"], validate=True)
        if (
            len(raw) > 16_000_000
            or digest(raw) != data["render"]["sha256"]
            or payload["id"] != digest(json.dumps(data, sort_keys=True))
        ):
            raise ValueError("Evidence or pixel hash mismatch")
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": model_text(data)}],
            }
        ]
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[prompt], images=[image], return_tensors="pt", padding=False).to(
            "cuda"
        )
        count = int(inputs.input_ids.shape[-1])
        if count > SPEC["max_input_tokens"]:
            raise ValueError("Evidence exceeds frozen context cap; never silently truncate")
        with torch.inference_mode():
            # Bypass the vocabulary projection. Only hidden states are required.
            output = model.model(
                **inputs, output_hidden_states=True, use_cache=False, return_dict=True
            )
            vector = output.hidden_states[SPEC["hidden_state_index"]][0, -1].float().cpu()
        if not torch.isfinite(vector).all():
            raise ValueError("Non-finite activations")
        results.append(
            {
                "id": payload["id"],
                "spec": SPEC,
                "activation": vector.tolist(),
                "dimensions": int(vector.shape[0]),
                "input_tokens": count,
                "generated_tokens": 0,
                "trainable_backbone_parameters": sum(
                    p.numel() for p in model.parameters() if p.requires_grad
                ),
                "pixel_sha256": data["render"]["sha256"],
            }
        )
        del output, inputs, vector
    return {
        "features": results,
        "gpu_seconds": time.monotonic() - started,
        "spec": SPEC,
        "backbone_frozen": True,
    }


def fit_probe(rows):
    require_cloud()
    from .activation_head import fit, metrics

    if len(rows) > 256:
        raise ValueError("Probe pilot has a 256-example cap")
    head = fit(rows)
    reports = {
        part: metrics(head, [r for r in rows if r["partition"] == part])
        for part in ("train", "dev", "test")
    }
    return {"head": head, "metrics": reports}
