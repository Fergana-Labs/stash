"""Benchmark tasks for intuitions: one decision each, in the product's example shape.

Rows: {"id", "item", "item_b" (pairs only), "label"}. Every task has a fixed,
label-stratified test set; training labels are drawn from the rest.

Data locations (none of it is committed):
  INTUITION_DATA   the old harness's cache (agentrewardbench.jsonl, gsm8k/, summaries_raw.jsonl)
  BENCH_DOWNLOADS  banking/test.csv (PolyAI Banking77), goemo/*.json (GoEmotions via HF datasets-server)
  EMAIL_EXAMPLES   a private export of the "Needs my action" intuition's labeled examples
"""

from __future__ import annotations

import csv
import glob
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("INTUITION_DATA", ROOT / "scripts" / "intuition_eval" / "data"))
DOWNLOADS = Path(os.environ.get("BENCH_DOWNLOADS", "bench_downloads"))
EMAIL = os.environ.get("EMAIL_EXAMPLES")
DEMO = ROOT / "backend" / "services" / "intuition" / "demo_support_replies.json"
TEST_SIZE = 60


def _h(value: str) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest()[:8], 16)


@dataclass
class Task:
    name: str
    title: str
    kind: str  # what kind of judgment, for the results table
    output_type: str  # choice | multi | preference
    description: str
    labels: list[dict]
    test: list[dict]
    pool: list[dict]


def stratified(rows: list[dict], n: int, seed: str, key=lambda r: r["label"]) -> list[dict]:
    """n rows spread across label values as evenly as the data allows, deterministically."""
    groups: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: _h(seed + r["id"])):
        groups.setdefault(key(r), []).append(r)
    out, queues = [], list(groups.values())
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop(0))
    return out


def _split(
    name: str, rows: list[dict], test_size: int = TEST_SIZE, key=lambda r: r["label"]
) -> tuple[list, list]:
    test = stratified(rows, test_size, name + ":test", key)
    ids = {r["id"] for r in test}
    return test, [r for r in rows if r["id"] not in ids]


def support() -> Task:
    spec = json.loads(DEMO.read_text())
    rows = [
        {
            "id": f"s{i}",
            "item": {"customer": e["customer"], "reply": e["reply"]},
            "label": e["label"],
        }
        for i, e in enumerate(spec["examples"])
    ]
    test, pool = _split("support", rows, test_size=20)
    return Task(
        "support",
        "Support reply review",
        "3-way quality call on short text",
        "choice",
        spec["description"],
        spec["labels"],
        test,
        pool,
    )


def arb() -> Task:
    records = [
        json.loads(line) for line in (DATA / "agentrewardbench.jsonl").read_text().splitlines()
    ]
    rows = [
        {"id": r["key"], "item": r["text"], "label": "success" if r["label"] == 1 else "failure"}
        for r in records
    ]
    test, pool = _split("arb", rows)
    return Task(
        "arb",
        "Web agent success (AgentRewardBench)",
        "binary verification of long agent trajectories",
        "choice",
        "Text transcripts of web agents attempting a user's goal in a browser: the goal, each step's "
        "reasoning and action, errors, the agent's final message, and an excerpt of the final page. "
        "Expert annotators judged whether the agent actually accomplished the goal. Agents often stop "
        "early, answer incorrectly, act on the wrong item, or claim success without completing the task.",
        [
            {"id": "success", "description": "The agent accomplished the user's goal."},
            {"id": "failure", "description": "The agent did not accomplish the goal."},
        ],
        test,
        pool,
    )


def gsm8k() -> Task:
    cache = [
        json.loads(line)
        for line in gzip.open(DATA / "gsm8k" / "frozen_qwen2p5_1p5b_gsm8k.jsonl.gz", "rt")
    ]
    by_prompt: dict[str, list[dict]] = {}
    for r in cache:
        by_prompt.setdefault(str(r["dataset_id"]), []).append(r)
    rows = []
    for d in sorted(by_prompt, key=lambda d: _h("gsm" + d))[:200]:
        samples = sorted(by_prompt[d], key=lambda r: int(r["sample_id"]))
        for want in (1.0, 0.0):  # one right and one wrong solution per problem when both exist
            pick = next((r for r in samples if float(r["reward"]) == want), None)
            if pick:
                rows.append(
                    {
                        "id": f"g{d}-{pick['sample_id']}",
                        "item": {"question": pick["question"], "solution": pick["text"]},
                        "label": "correct" if want == 1.0 else "incorrect",
                    }
                )
    test, pool = _split("gsm8k", rows)
    return Task(
        "gsm8k",
        "Math answer grading (GSM8K)",
        "binary correctness of a small model's solutions",
        "choice",
        "Solutions to grade-school math word problems written by a small language model (Qwen2.5-1.5B), "
        "ending with 'Final answer: <number>'. Decide whether the solution's final answer is correct. "
        "Solutions may misread the problem, make arithmetic slips, use the wrong operation, or be cut off.",
        [
            {"id": "correct", "description": "The final answer is correct."},
            {"id": "incorrect", "description": "The final answer is wrong or missing."},
        ],
        test,
        pool,
    )


def summaries() -> Task:
    raw = [json.loads(line) for line in (DATA / "summaries_raw.jsonl").read_text().splitlines()]
    mine = [r for r in raw if r["worker"] == "RMwrIV50cNusBthNvLs1wSNdqFpQAg"]
    rows = []
    for i, r in enumerate(mine):
        post = f"{r['info'].get('title') or ''}\n\n{(r['info'].get('post') or r['info'].get('article') or '')[:3000]}"
        a, b = (s["text"].strip() for s in r["summaries"])
        rows.append(
            {
                "id": f"c{i}",
                "item": {"post": post, "summary": a},
                "item_b": {"post": post, "summary": b},
                "label": "a" if r["choice"] == 0 else "b",
            }
        )
    test, pool = _split("summaries", rows)
    return Task(
        "summaries",
        "One person's summary taste (OpenAI TL;DR)",
        "pairwise preference of one human labeler",
        "preference",
        "TL;DR summaries of Reddit posts, compared by one specific human labeler from OpenAI's "
        "summarize-from-feedback study. Predict which of two summaries this particular labeler prefers. "
        "Labelers weighed accuracy, coverage of the main points, coherence and concision, and each had their own taste.",
        [],
        test,
        pool,
    )


BANKING = [
    "card_arrival",
    "card_delivery_estimate",
    "card_not_working",
    "card_swallowed",
    "declined_card_payment",
    "lost_or_stolen_card",
    "compromised_card",
    "activate_my_card",
]
BANKING_DESC = {
    "card_arrival": "Asking where a card they ordered is / that it hasn't arrived",
    "card_delivery_estimate": "Asking how long card delivery takes, before it is late",
    "card_not_working": "The card doesn't work in general",
    "card_swallowed": "An ATM kept (swallowed) the card",
    "declined_card_payment": "A specific card payment was declined",
    "lost_or_stolen_card": "The card is lost or was stolen",
    "compromised_card": "Worried the card details were compromised or used by someone else",
    "activate_my_card": "How to activate a card",
}


def banking() -> Task:
    with open(DOWNLOADS / "banking" / "test.csv") as f:
        rows = [
            {"id": f"b{i}", "item": r["text"], "label": r["category"]}
            for i, r in enumerate(csv.DictReader(f))
            if r["category"] in BANKING
        ]
    test, pool = _split("banking", rows, test_size=64)
    return Task(
        "banking",
        "Bank support intents (Banking77, 8 card intents)",
        "fine-grained 8-way intent",
        "choice",
        "Customer messages to a bank's support chat. Route each to the one intent it expresses. The eight "
        "intents are all about cards and are easy to confuse.",
        [{"id": k, "description": v} for k, v in BANKING_DESC.items()],
        test,
        pool,
    )


EMOTIONS = ["anger", "annoyance", "disappointment", "disapproval", "sadness"]


def goemotions() -> Task:
    files = sorted(glob.glob(str(DOWNLOADS / "goemo" / "*.json")), key=lambda p: int(Path(p).stem))
    names = json.load(open(files[0]))["features"][1]["type"]["feature"]["names"]
    rows = []
    for f in files:
        for r in json.load(open(f)).get("rows", []):
            found = sorted({names[i] for i in r["row"]["labels"]} & set(EMOTIONS))
            rows.append(
                {"id": r["row"]["id"], "item": r["row"]["text"], "label": "+".join(found) or "none"}
            )
    # Keep a realistic mix: every comment with one of the five emotions, and as many without.
    with_emotion = [r for r in rows if r["label"] != "none"]
    without = sorted((r for r in rows if r["label"] == "none"), key=lambda r: _h("ge" + r["id"]))[
        : len(with_emotion)
    ]
    rows = with_emotion + without
    first = lambda r: r["label"].split("+")[0]  # noqa: E731 -- stratify on the first emotion
    test, pool = _split("goemotions", rows, key=first)
    return Task(
        "goemotions",
        "Negative emotions in comments (GoEmotions, multi-label)",
        "multi-label: any of 5 emotions, or none",
        "multi",
        "Reddit comments annotated by raters for the emotions they express. Flag every one of these five "
        "negative emotions the comment expresses; several can apply, or none.",
        [{"id": e, "description": e} for e in EMOTIONS],
        test,
        pool,
    )


def email() -> Task | None:
    if not EMAIL or not Path(EMAIL).exists():
        return None
    rows = [
        {"id": e["id"], "item": e["item"], "label": e["label"], "_split": e["split"]}
        for e in json.load(open(EMAIL))
        if e["label"] and not e["needs_review"]
    ]
    # The intuition's own held-out split is the test set, so numbers match the product.
    test = [r for r in rows if r["_split"] == "eval"]
    pool = [r for r in rows if r["_split"] != "eval"]
    return Task(
        "email",
        "Needs my action (Sam's inbox, self-supervised)",
        "binary, personal, labels from behavior",
        "choice",
        "Decide whether this email to Sam Liu (personal inbox) needs him to do something: reply, confirm, "
        "provide a document, pay, sign, RSVP, or call.",
        [
            {"id": "action", "description": "Sam needs to do something"},
            {
                "id": "no_action",
                "description": "Nothing for Sam to do: notifications, receipts, blasts, FYIs, closers",
            },
        ],
        test,
        pool,
    )


def all_tasks() -> list[Task]:
    return [
        t
        for t in (support(), arb(), gsm8k(), summaries(), banking(), goemotions(), email())
        if t is not None
    ]


def sample(pool: list[dict], n: int, seed: str) -> list[dict]:
    first = lambda r: r["label"].split("+")[0]  # noqa: E731
    if n >= len(pool):
        return list(pool)
    return stratified(pool, n, seed, first)


__all__ = ["Task", "all_tasks", "sample"]
