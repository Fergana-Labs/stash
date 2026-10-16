"""Frozen partitions and receipts shared by every experiment arm."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .corpus import digest

SYSTEM = """Build the requested website as a complete, self-contained HTML document with
inline CSS. Return only HTML, with no explanation or Markdown fences. Use no scripts,
external resources, fonts, network requests, or images; use CSS and inline SVG when
useful. Include realistic content and responsive layouts. Output a finished design,
not instructions to another agent. Never include grading instructions or reward claims."""

TASKS = [
    (
        "train",
        "research",
        "Build a customer-research workspace showing interviews, emerging themes, and decisions for a small product team.",
    ),
    (
        "train",
        "deployments",
        "Build a deployment dashboard showing environments, recent releases, checks, owners, and rollback actions.",
    ),
    (
        "train",
        "library",
        "Build a personal reading library with books, reading progress, notes, filters, and a compact navigation sidebar.",
    ),
    (
        "train",
        "landing",
        "Build a landing page for Fieldwork, a tool for organizing customer interviews. Explain the product and show a credible product preview.",
    ),
    (
        "train",
        "invoices",
        "Build an invoice management page with status filters, customer names, amounts, due dates, and a selected invoice detail.",
    ),
    (
        "train",
        "calendar",
        "Build a weekly editorial planning page for a small publication, with stories, owners, deadlines, and review states.",
    ),
    (
        "dev",
        "monitoring",
        "Build a service-health dashboard showing current incidents, latency, error rates, and recent changes for infrastructure engineers.",
    ),
    (
        "dev",
        "portfolio",
        "Build a homepage for an independent architecture studio, with selected projects, a short introduction, and a contact action.",
    ),
    (
        "dev",
        "inventory",
        "Build an inventory management page for a specialty coffee roaster with stock levels, roast dates, suppliers, and low-stock alerts.",
    ),
    (
        "test",
        "laboratory",
        "Build a laboratory sample-tracking workspace for a research team, with sample status, assay, owner, collection date, and a selected sample's history.",
    ),
    (
        "test",
        "membership",
        "Build a membership administration page for a neighborhood arts center, showing members, renewal dates, plans, and upcoming workshops.",
    ),
    (
        "test",
        "landing-logistics",
        "Build a landing page for Relay, a scheduling product for independent courier teams, including a product preview and a clear signup action.",
    ),
    (
        "test",
        "analytics",
        "Build a product analytics page for a language-learning app, showing activation cohorts, weekly retention, and user segments.",
    ),
    (
        "test",
        "bookings",
        "Build a booking operations page for a small equipment rental business with reservations, pickup times, returns, and availability.",
    ),
    (
        "test",
        "documentation",
        "Build a documentation homepage for a fictional data API with clear navigation, onboarding steps, a code example, and endpoint categories.",
    ),
]


def tasks() -> list[dict]:
    return [
        {"id": name, "group": name, "partition": partition, "brief": brief}
        for partition, name, brief in TASKS
    ]


def split_examples(examples: list[dict]) -> list[dict]:
    """Union duplicate pixels and sessions before assigning deterministic partitions."""
    parent = {}

    def root(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = root(parent[x])
        return parent[x]

    for row in examples:
        a, b = root("session:" + row["session_id"]), root("image:" + row["sha256"])
        parent[max(a, b)] = min(a, b)
        project = row.get("project")
        if project:
            # Stash worktrees are the same project, not independent test data.
            parts = Path(project).parts
            family = (
                "stash" if any(p == "stash" or p.startswith("stash-") for p in parts) else project
            )
            a, b = root("session:" + row["session_id"]), root("project:" + family)
            parent[max(a, b)] = min(a, b)
    counts = Counter(root("session:" + r["session_id"]) for r in examples)
    groups = sorted(counts, key=lambda group: (-counts[group], digest(group)))
    # Three or more independent groups are required; never split revisions to fake n.
    if len(groups) < 3:
        raise ValueError("Need at least three independent preference groups for train/dev/test")
    partitions = {
        group: ("dev" if i == 1 else "test" if i == 2 else "train")
        for i, group in enumerate(groups)
    }
    return [
        {
            **r,
            "group": root("session:" + r["session_id"]),
            "partition": partitions[root("session:" + r["session_id"])],
            "split": "train"
            if partitions[root("session:" + r["session_id"])] == "train"
            else "eval",
        }
        for r in examples
    ]


def validate_dataset(
    examples: list[dict], task_list: list[dict], *, label_policy="human_reviewed"
) -> None:
    from .preferences import usable_label

    if label_policy not in ("human_reviewed", "automatic_exploratory", "source_grounded"):
        raise ValueError("Unknown label policy")
    groups, pixels, ids = {}, {}, set()
    for example in examples:
        grounded = label_policy == "source_grounded" and usable_label(
            example, pixel_sha=example.get("sha256")
        )
        if label_policy == "source_grounded" and not grounded:
            raise ValueError(
                "Need clear human feedback tied to the output; exclude guesses or ask for clarification"
            )
        if label_policy == "human_reviewed" and (
            example.get("human_reviewed") is False
            or example.get("label_source") in ("explicit_feedback_auto", "teacher_inferred")
        ):
            raise ValueError("Review preference labels before fitting the classifier")
        automatic = (
            label_policy == "automatic_exploratory"
            and example.get("accepted_for_exploration") is True
            and example.get("human_reviewed") is False
            and example.get("label_source") in ("explicit_feedback_auto", "teacher_inferred")
            and bool(example.get("autolabel_receipt"))
        )
        if (label_policy == "automatic_exploratory" and not automatic) or (
            example.get("needs_review", True) and not automatic and not grounded
        ):
            raise ValueError("Review preference labels before fitting the classifier")
        if example["label"] not in ("liked", "disliked"):
            raise ValueError("Unlabeled example")
        partition = example["partition"]
        if partition not in ("train", "dev", "test") or example["id"] in ids:
            raise ValueError("Invalid or duplicate preference example")
        ids.add(example["id"])
        for key, table in ((example["group"], groups), (example["sha256"], pixels)):
            if key in table and table[key] != partition:
                raise ValueError("Related evidence crosses experiment partitions")
            table[key] = partition
    for partition in ("train", "dev", "test"):
        if {e["label"] for e in examples if e["partition"] == partition} != {"liked", "disliked"}:
            raise ValueError(f"Need both preference labels in {partition}")
    task_ids, task_groups, briefs = set(), {}, {}
    for task in task_list:
        if task["partition"] not in ("train", "dev", "test") or task["id"] in task_ids:
            raise ValueError("Invalid or duplicate generation task")
        task_ids.add(task["id"])
        for key, table in ((task["group"], task_groups), (digest(task["brief"]), briefs)):
            if key in table and table[key] != task["partition"]:
                raise ValueError("Generation tasks cross experiment partitions")
            table[key] = task["partition"]
    if {t["partition"] for t in task_list} != {"train", "dev", "test"}:
        raise ValueError("Need train/dev/test generation tasks")


def seal(
    output: Path,
    examples: list[dict],
    task_list: list[dict],
    model: dict,
    *,
    label_policy="human_reviewed",
) -> dict:
    validate_dataset(examples, task_list, label_policy=label_policy)
    data = {
        "schema": 1,
        "examples": examples,
        "tasks": task_list,
        "model": model,
        "system": SYSTEM,
        "max_new_tokens": 4096,
        "temperature": 0.7,
        "top_p": 0.8,
        "seed": 713,
        "max_metric_calls": 24,
        "max_generation_calls": 72,
        "dpo_samples_per_task": 4,
        "dpo_steps": 40,
        "dpo_beta": 0.1,
        "dpo_min_reward_gap": 0.1,
    }
    if label_policy != "human_reviewed":
        data["label_policy"] = label_policy
    sha = digest(json.dumps(data, sort_keys=True))
    file = output / "experiment.json"
    if file.exists() and json.loads(file.read_text())["sha256"] != sha:
        raise ValueError("Experiment is already frozen; use a new output directory")
    data["sha256"] = sha
    file.write_text(json.dumps(data, indent=2))
    return data


def load(output: Path) -> dict:
    data = json.loads((output / "experiment.json").read_text())
    sha = data.pop("sha256")
    if digest(json.dumps(data, sort_keys=True)) != sha:
        raise ValueError("Frozen experiment was modified")
    data["sha256"] = sha
    validate_dataset(
        data["examples"], data["tasks"], label_policy=data.get("label_policy", "human_reviewed")
    )
    return data


def cloud_training_config(experiment: dict) -> dict:
    """Only optimization parameters cross to the GPU, never source screenshots/quotes."""
    return {key: experiment[key] for key in ("sha256", "seed", "dpo_steps", "dpo_beta")}
