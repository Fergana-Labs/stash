"""The GPU side: one function that trains a voice, one class that writes with
it, one that judges drafts, and the web endpoint the backend talks to.

Everything here runs in Fergana's Modal workspace. The backend never sees
weights or adapters; it sends passages and gets back an adapter path and a
style profile, then sends prompts and gets back drafts.

    cd gpu && modal deploy -m stylewriter.modal_app

prints the `api` endpoint URL, which becomes STYLEWRITER_GPU_URL. Before the
first deploy, create the shared secret the backend authenticates with:

    modal secret create stylewriter-api STYLEWRITER_GPU_SECRET=<random>
"""

# No `from __future__ import annotations` here: Modal inspects real annotation
# objects on class parameters and cannot resolve stringized ones.

import modal

APP_NAME = "stylewriter"
ADAPTERS_VOLUME = "stylewriter-adapters"
# The workspace already holds every base model this app uses under this
# volume's HF cache (tens of gigabytes); sharing it is what makes a fresh
# deploy start in minutes instead of re-downloading.
CACHE_VOLUME = "voiceprint-cache"

PREP_MODEL = "Qwen/Qwen2.5-7B-Instruct"
BASE_MODEL = "Qwen/Qwen2.5-14B-Instruct"
SUPPORTED_MODELS = {BASE_MODEL}

TRAIN_GPU = "A100-80GB"
SERVE_GPU = "A100-80GB"
DETECTOR_GPU = "L40S"

LORA_RANK = 16
LORA_ALPHA = 32
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
LEARNING_RATE = 1e-4
# Three epochs keep the voice while leaving the brief load-bearing; more
# drove training loss to zero and the adapter began ignoring its input.
EPOCHS = 3
GRAD_ACCUM = 2
MAX_SEQ_LEN = 2048

MAX_CHUNKS = 500
MAX_TEXT_CHARS = 30_000
MIN_TRAIN_WORDS = 1_000

app = modal.App(APP_NAME)

adapters_volume = modal.Volume.from_name(ADAPTERS_VOLUME, create_if_missing=True)
cache_volume = modal.Volume.from_name(CACHE_VOLUME, create_if_missing=True)
VOLUMES = {"/adapters": adapters_volume, "/cache": cache_volume}

# `add_local_python_source` must come last in each chain: Modal refuses build
# steps after local files are added, so a code edit never rebuilds the image.
_base = modal.Image.debian_slim(python_version="3.12").env({"HF_HOME": "/cache/hf"})

train_image = _base.pip_install(
    "torch==2.13.0",
    "transformers==4.57.6",
    "peft==0.20.0",
    "accelerate>=1.0",
    "huggingface_hub",
).add_local_python_source("stylewriter")

# vLLM's flashinfer backend compiles kernels at engine start and needs nvcc,
# so serving runs on a CUDA devel base rather than debian_slim.
serve_image = (
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu24.04", add_python="3.12")
    .env({"HF_HOME": "/cache/hf"})
    .pip_install("vllm==0.27.1", "huggingface_hub")
    .add_local_python_source("stylewriter")
)

detector_image = _base.pip_install(
    "torch==2.13.0",
    "transformers==4.57.6",
    "accelerate>=1.0",
    "huggingface_hub",
).add_local_python_source("stylewriter")

web_image = _base.pip_install("fastapi[standard]").add_local_python_source("stylewriter")


# ── Training ──────────────────────────────────────────────────────────


@app.function(image=train_image, gpu=TRAIN_GPU, volumes=VOLUMES, timeout=3600)
def train_adapter(name: str, chunks: list[dict], model: str) -> dict:
    """Passages in, adapter on the volume out.

    Two model loads in one container: the instruct model writes the briefs
    and generic rewrites, then the base model learns to write passages from
    them. The style profile is fitted here too, on the same passages, so the
    backend stores one result and never runs stylometry itself."""
    import gc
    import time

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from stylewriter import stylometry
    from stylewriter.prep import DEGRADE_REQUEST, NOTES_REQUEST, pairs_for_chunk, parse_notes

    started = time.time()

    print(f"[prep] {len(chunks)} passages -> briefs and generic rewrites")
    prep_tokenizer = AutoTokenizer.from_pretrained(PREP_MODEL)
    prep_model = AutoModelForCausalLM.from_pretrained(
        PREP_MODEL, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    prep_tokenizer.padding_side = "left"
    if prep_tokenizer.pad_token is None:
        prep_tokenizer.pad_token = prep_tokenizer.eos_token

    def ask(requests: list[str], max_new_tokens: int, batch_size: int = 8) -> list[str]:
        answers = []
        for start in range(0, len(requests), batch_size):
            prompts = [
                prep_tokenizer.apply_chat_template(
                    [{"role": "user", "content": r}], tokenize=False, add_generation_prompt=True
                )
                for r in requests[start : start + batch_size]
            ]
            batch = prep_tokenizer(prompts, return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                out = prep_model.generate(
                    **batch,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=prep_tokenizer.pad_token_id,
                )
            answers.extend(
                prep_tokenizer.decode(row[batch["input_ids"].shape[1] :], skip_special_tokens=True)
                for row in out
            )
        return answers

    notes = [
        parse_notes(a) for a in ask([NOTES_REQUEST.format(passage=c["text"]) for c in chunks], 200)
    ]
    degraded = ask([DEGRADE_REQUEST.format(passage=c["text"]) for c in chunks], 900)

    # Dropping the last reference frees the 7B model before the 14B loads.
    prep_model = None
    gc.collect()
    torch.cuda.empty_cache()

    chats = []
    for chunk, chunk_notes, generic in zip(chunks, notes, degraded, strict=True):
        if not chunk_notes:
            continue
        chats.extend(pairs_for_chunk(chunk, chunk_notes, generic))
    print(f"[prep] {len(chats)} training pairs")

    print(f"[train] loading {model}")
    tokenizer = AutoTokenizer.from_pretrained(model)
    if tokenizer.chat_template is None:
        raise ValueError(f"{model} has no chat template; an instruct model is required")
    base = AutoModelForCausalLM.from_pretrained(
        model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    peft_model = get_peft_model(
        base,
        LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_ALPHA,
            target_modules=LORA_TARGETS,
            lora_dropout=0.05,
            task_type="CAUSAL_LM",
        ),
    )

    # Loss only on the assistant span: the model learns to write the
    # passage, not to predict the brief.
    examples = []
    for chat in chats:
        prompt_ids = tokenizer.apply_chat_template(
            chat[:-1], tokenize=True, add_generation_prompt=True
        )
        full_ids = tokenizer.apply_chat_template(chat, tokenize=True)
        full_ids = full_ids[:MAX_SEQ_LEN]
        labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :]
        examples.append((full_ids, labels[: len(full_ids)]))

    optimizer = torch.optim.AdamW(
        (p for p in peft_model.parameters() if p.requires_grad), lr=LEARNING_RATE
    )
    peft_model.train()
    for epoch in range(EPOCHS):
        total = 0.0
        for i, (ids, labels) in enumerate(examples):
            input_ids = torch.tensor([ids], device="cuda")
            label_ids = torch.tensor([labels], device="cuda")
            loss = peft_model(input_ids=input_ids, labels=label_ids).loss / GRAD_ACCUM
            loss.backward()
            total += loss.item() * GRAD_ACCUM
            if (i + 1) % GRAD_ACCUM == 0 or i == len(examples) - 1:
                optimizer.step()
                optimizer.zero_grad()
        print(f"[train] epoch {epoch + 1}/{EPOCHS} loss {total / max(len(examples), 1):.3f}")

    adapter_path = f"/adapters/{name}"
    peft_model.save_pretrained(adapter_path)
    adapters_volume.commit()

    return {
        "adapter_path": adapter_path,
        "pairs": len(chats),
        "profile": stylometry.fit([c["text"] for c in chunks]).to_dict(),
        "seconds": round(time.time() - started),
    }


# ── Serving ───────────────────────────────────────────────────────────


@app.cls(
    image=serve_image,
    gpu=SERVE_GPU,
    volumes=VOLUMES,
    scaledown_window=600,
    timeout=1200,
)
class Writer:
    """One resident base model; adapters are hot-swapped per request. A LoRA
    is a delta on specific weights, so a second base would be a second
    container, not a second adapter."""

    @modal.enter()
    def load(self) -> None:
        from vllm import LLM

        self.llm = LLM(
            model=BASE_MODEL,
            enable_lora=True,
            max_lora_rank=LORA_RANK,
            max_model_len=4096,
            gpu_memory_utilization=0.85,
            download_dir="/cache/hf",
        )
        self.tokenizer = self.llm.get_tokenizer()

    @modal.method()
    def generate(
        self, adapter_path: str, prompt: dict, n: int, sampling: dict, max_tokens: int
    ) -> list[dict]:
        import zlib

        from vllm import SamplingParams
        from vllm.lora.request import LoRARequest

        text = self.tokenizer.apply_chat_template(
            prompt["messages"], tokenize=False, add_generation_prompt=True
        )
        params = SamplingParams(n=n, max_tokens=max_tokens, **sampling)
        lora = LoRARequest(adapter_path, zlib.crc32(adapter_path.encode()) or 1, adapter_path)
        outputs = self.llm.generate([text], params, lora_request=lora, use_tqdm=False)
        return [{"text": o.text, "finish_reason": o.finish_reason} for o in outputs[0].outputs]


@app.cls(image=detector_image, gpu=DETECTOR_GPU, volumes=VOLUMES, scaledown_window=600)
class Detector:
    """Binoculars on the Falcon pair. Its own container so two 7B models are
    not competing with the writer's KV cache for one GPU."""

    @modal.enter()
    def load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from stylewriter.binoculars import OBSERVER_MODEL, PERFORMER_MODEL

        self.tokenizer = AutoTokenizer.from_pretrained(OBSERVER_MODEL)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.observer = AutoModelForCausalLM.from_pretrained(
            OBSERVER_MODEL, torch_dtype=torch.bfloat16, device_map="cuda"
        ).eval()
        self.performer = AutoModelForCausalLM.from_pretrained(
            PERFORMER_MODEL, torch_dtype=torch.bfloat16, device_map="cuda"
        ).eval()

    @modal.method()
    def read_many(self, texts: list[str]) -> list[float]:
        """p_human for each text.

        As in the reference implementation: the numerator is the performer's
        log-perplexity of the text, the denominator the cross-entropy of the
        observer's distribution against the performer's log-probabilities.
        Swapping the two roles shifts every score and reads real writing as
        machine text."""
        import torch

        from stylewriter.binoculars import p_human

        readings = []
        for text in texts:
            batch = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(
                "cuda"
            )
            with torch.no_grad():
                observer_logits = self.observer(**batch).logits[:, :-1].float()
                performer_logits = self.performer(**batch).logits[:, :-1].float()
            targets = batch["input_ids"][:, 1:]
            performer_log_probs = torch.log_softmax(performer_logits, dim=-1)
            ppl = -performer_log_probs.gather(-1, targets.unsqueeze(-1)).squeeze(-1).mean()
            observer_probs = torch.softmax(observer_logits, dim=-1)
            x_ppl = -(observer_probs * performer_log_probs).sum(-1).mean()
            readings.append(p_human((ppl / x_ppl).item()))
        return readings


# ── Requests ──────────────────────────────────────────────────────────


def parse_training(item: dict) -> tuple[str, list[dict], str]:
    name = item.get("name")
    if not isinstance(name, str) or not name.startswith("model_") or len(name) > 96:
        raise ValueError("invalid model name")
    model = item.get("model")
    if model not in SUPPORTED_MODELS:
        raise ValueError("unsupported base model")
    chunks = item.get("chunks")
    if not isinstance(chunks, list) or not chunks or len(chunks) > MAX_CHUNKS:
        raise ValueError(f"chunks must be a non-empty list of at most {MAX_CHUNKS} passages")
    total = 0
    clean = []
    for index, chunk in enumerate(chunks):
        text = chunk.get("text") if isinstance(chunk, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"chunk {index + 1} has invalid text")
        words = len(text.split())
        if words < 25:
            raise ValueError(f"chunk {index + 1} is too short")
        length = chunk.get("length")
        if length not in ("short", "medium", "long"):
            raise ValueError(f"chunk {index + 1} has an invalid length label")
        clean.append({"text": text.strip(), "words": words, "length": length})
        total += words
    if total < MIN_TRAIN_WORDS:
        raise ValueError(f"at least {MIN_TRAIN_WORDS:,} usable words are required")
    return name, clean, model


def parse_generation(item: dict) -> dict:
    """Bound every caller-controlled field before an adapter is loaded."""
    from stylewriter.scaffold import LENGTHS

    adapter_path = item.get("adapter_path")
    if (
        not isinstance(adapter_path, str)
        or ".." in adapter_path
        or not adapter_path.startswith("/adapters/model_")
    ):
        raise ValueError("invalid adapter path")
    if item.get("model") not in SUPPORTED_MODELS:
        raise ValueError("unsupported base model")
    operation = item.get("operation")
    if operation not in ("write", "continue", "rewrite", "edit_span", "score"):
        raise ValueError("unknown operation")
    length = item.get("length", "medium")
    if length not in LENGTHS:
        raise ValueError("length must be short, medium, or long")
    notes = item.get("notes", [])
    if not isinstance(notes, list) or len(notes) > 12 or any(not isinstance(n, str) for n in notes):
        raise ValueError("notes must be at most 12 strings")
    text_fields = {}
    for key in ("preceding_text", "text", "replacement_draft"):
        value = item.get(key, "")
        if not isinstance(value, str) or len(value) > MAX_TEXT_CHARS:
            raise ValueError(f"{key} is too long")
        text_fields[key] = value
    profile = item.get("style_profile")
    if not isinstance(profile, dict):
        raise ValueError("style_profile is required")

    if operation == "write" and not [n for n in notes if n.strip()]:
        raise ValueError("write requires at least one note")
    if operation == "continue" and not text_fields["preceding_text"].strip():
        raise ValueError("continue requires preceding_text")
    if operation in ("rewrite", "score") and not text_fields["text"].strip():
        raise ValueError(f"{operation} requires text")
    start = item.get("start")
    end = item.get("end")
    if operation == "edit_span":
        text = text_fields["text"]
        if not (isinstance(start, int) and isinstance(end, int)) or not (
            0 <= start < end <= len(text)
        ):
            raise ValueError("edit_span requires valid start/end offsets within text")
        if not text_fields["replacement_draft"].strip():
            raise ValueError("edit_span requires a replacement_draft")
    return {
        "adapter_path": adapter_path,
        "operation": operation,
        "length": length,
        "notes": [n.strip()[:500] for n in notes if n.strip()],
        "start": start,
        "end": end,
        "style_profile": profile,
        **{k: v.strip() if k != "text" else v for k, v in text_fields.items()},
    }


# ── Jobs ──────────────────────────────────────────────────────────────


@app.function(image=web_image, timeout=3700, max_containers=4)
def train_job(item: dict) -> dict:
    name, chunks, model = parse_training(item)
    return train_adapter.remote(name=name, chunks=chunks, model=model)


@app.function(image=web_image, timeout=1000, max_containers=8)
def generate_job(item: dict) -> dict:
    from stylewriter import selection, stylometry
    from stylewriter.scaffold import (
        MAX_TOKENS,
        SAMPLING,
        rewrite_prompt,
        trim_to_sentence,
        write_prompt,
    )

    request = parse_generation(item)
    operation = request["operation"]
    profile = stylometry.Profile.from_dict(request["style_profile"])
    if operation == "edit_span":
        prompt = rewrite_prompt(request["replacement_draft"])
    elif operation == "rewrite":
        prompt = rewrite_prompt(request["text"])
    else:
        prompt = write_prompt(
            request["notes"],
            request["length"],
            preceding_text=request["preceding_text"] if operation == "continue" else "",
        )
    length = "medium" if operation in ("rewrite", "edit_span") else request["length"]

    def draw(count: int) -> list[str]:
        candidates = Writer().generate.remote(
            adapter_path=request["adapter_path"],
            prompt=prompt.to_dict(),
            n=count,
            sampling=SAMPLING,
            max_tokens=MAX_TOKENS[length],
        )
        return [
            trim_to_sentence(c["text"]) if c["finish_reason"] == "length" else c["text"].strip()
            for c in candidates
        ]

    chosen = selection.best_of_n(
        draw,
        lambda text: stylometry.similarity(profile, text),
        Detector().read_many.remote,
    )
    text = chosen.text
    if operation == "edit_span":
        source = request["text"]
        text = source[: request["start"]] + chosen.text + source[request["end"] :]
    return {
        "text": text,
        "style_score": chosen.style,
        "p_human": chosen.p_human,
        "draws": chosen.draws,
        "soft_failed": chosen.soft_failed,
        "alternates": [{"text": c.text, "style_score": c.style} for c in chosen.alternates[:3]],
        "warning": (
            "No candidate cleared the detector; this is the closest. Change the notes and "
            "regenerate rather than editing this text."
            if chosen.soft_failed
            else "Verify every fact before using this; the model trades accuracy for voice."
        ),
    }


def score_now(item: dict) -> dict:
    from stylewriter import stylometry

    request = parse_generation(item)
    profile = stylometry.Profile.from_dict(request["style_profile"])
    return {
        "style_score": stylometry.similarity(profile, request["text"]),
        "p_human": Detector().read_many.remote([request["text"]])[0],
    }


# The one caller is the Stash backend, which holds the same secret. A shared
# secret rather than Modal proxy auth because proxy tokens can only be minted
# in the dashboard; this one is created with `modal secret create`.
API_SECRET = modal.Secret.from_name("stylewriter-api")


@app.function(image=web_image, timeout=300, max_containers=8, secrets=[API_SECRET])
@modal.asgi_app()
def api():
    """The one door. `op` picks what happens; jobs come back as a call id,
    `result` reports on one, `score` answers inline. A FastAPI app rather
    than a bare endpoint so the secret can be read from a header."""
    import hmac
    import os
    from typing import Annotated

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import JSONResponse

    web = FastAPI()
    expected = f"Bearer {os.environ['STYLEWRITER_GPU_SECRET']}"

    @web.post("/")
    def handle(item: dict, authorization: Annotated[str, Header()] = ""):
        if not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="bad secret")
        op = item.get("op")
        try:
            if op == "train_start":
                parse_training(item)
                return {"call_id": train_job.spawn(item).object_id}
            if op == "generate_start":
                parse_generation(item)
                return {"call_id": generate_job.spawn(item).object_id}
            if op == "score":
                return score_now(item)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if op == "result":
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not call_id.startswith("fc-"):
                raise HTTPException(status_code=400, detail="invalid call id")
            try:
                return modal.FunctionCall.from_id(call_id).get(timeout=0)
            except TimeoutError:
                return JSONResponse(status_code=202, content={"status": "pending"})
            except Exception as error:  # the job itself raised; surface its message
                raise HTTPException(status_code=500, detail=str(error)) from error
        raise HTTPException(status_code=400, detail=f"unknown op {op!r}")

    return web
