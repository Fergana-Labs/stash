"""Prepare a small review queue from real history; never train on unreviewed labels."""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import split_examples
from .runtime import Stash


def choose(proposals: list[dict], limit=24):
    eligible = [r for r in proposals if r["label"] != "unknown"]
    # Balance label, session, and visual hash; do not fill the queue with one long chat.
    eligible.sort(
        key=lambda r: (
            r["label"] != "liked",
            r["scope"] not in ("overall", "reference"),
            r["session_id"],
            r["line"],
        )
    )
    chosen, hashes, counts = [], set(), {}
    for cap in (2, 4, limit):
        for row in eligible:
            if len(chosen) >= limit:
                break
            key = (row["session_id"], row["label"])
            if row["sha256"] in hashes or counts.get(key, 0) >= cap:
                continue
            chosen.append(row)
            hashes.add(row["sha256"])
            counts[key] = counts.get(key, 0) + 1
    return chosen


def prepare(output: Path, stash: Stash, *, limit=24):
    path = output / "calibration.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    if previous and previous["complete"]:
        return {k: v for k, v in previous.items() if k != "examples"}
    proposals = [json.loads(s) for s in (output / "proposals.jsonl").read_text().splitlines()]
    selected = choose(proposals, limit)
    projects = {
        r["session_id"]: r["project"]
        for s in (output / "candidates.jsonl").read_text().splitlines()
        if (r := json.loads(s))
    }
    selected = [{**r, "project": projects[r["session_id"]]} for r in selected]
    if not selected:
        raise ValueError(
            "No grounded visual preference proposals; inspect extraction before continuing"
        )
    # Partition now, before criteria, skills, or classifier training can inspect labels.
    selected = previous["selected"] if previous else split_examples(selected)
    definition = {
        "name": "[History] Henry’s UI taste · calibration",
        "description": "Does this website or product interface match Henry's visual preferences? Judge only visible design, with the new task brief as context.",
        "output_type": "choice",
        "labels": [
            {"id": "liked", "description": "Henry would keep this as a visual reference."},
            {"id": "disliked", "description": "Henry would request visual changes."},
        ],
        "rubric": [],
    }
    record = previous or {
        "source": "real_local_codex_history",
        "examples": [],
        "selected": selected,
        "complete": False,
    }
    if "model_id" not in record:
        record["model_id"] = stash.call("POST", "/intuitions", json=definition)["model"]["id"]
        path.write_text(json.dumps(record, indent=2))
    if "test_review_model_id" not in record:
        record["test_review_model_id"] = stash.call(
            "POST",
            "/intuitions",
            json={**definition, "name": "[History] Henry’s UI taste · held-out review"},
        )["model"]["id"]
    model_id, test_model_id = record["model_id"], record["test_review_model_id"]
    path.write_text(json.dumps(record, indent=2))
    for proposal in selected:
        if any(e["id"] == proposal["id"] for e in record["examples"]):
            continue
        image = stash.image(Path(proposal["file"]))
        # Human criticism belongs in the label note, never in classifier input.
        item = {
            "kind": "website",
            "brief": "A website or product interface judged for Henry's visual preferences.",
            "render": image,
        }
        note = f"Suggested {proposal['label']}: {proposal['preference']}\nHenry’s exact feedback: {proposal['quote']}\nSource: Codex {proposal['session_id']}, turn line {proposal['line']}, image {proposal['image_index']}."
        # A separate review-only container keeps final-test pixels out of the classifier.
        native_model = test_model_id if proposal["partition"] == "test" else model_id
        examples = stash.call(
            "POST",
            f"/intuitions/{native_model}/examples",
            json={
                "examples": [
                    {
                        "item": item,
                        "label": proposal["label"],
                        "split": proposal["split"],
                        "needs_review": True,
                        "note": note,
                    }
                ]
            },
        )
        record["examples"].append(
            {
                **proposal,
                "native_id": examples[0]["id"],
                "native_model_id": native_model,
                "item": item,
            }
        )
        path.write_text(json.dumps(record, indent=2))
        print(
            json.dumps(
                {
                    "phase": "calibration",
                    "prepared": len(record["examples"]),
                    "total": len(selected),
                }
            ),
            flush=True,
        )
    session = stash.call("POST", "/model-wizard/sessions", json={"model_id": model_id})
    record.update(
        session_id=session["id"],
        wizard_path=f"/reward-models/wizard/{session['id']}",
        pending_review=sum(e["native_id"] is not None for e in record["examples"]),
        final_test_labels="pending separate review",
    )
    test_session = stash.call("POST", "/model-wizard/sessions", json={"model_id": test_model_id})
    record["test_wizard_path"] = f"/reward-models/wizard/{test_session['id']}"
    record["complete"] = True
    path.write_text(json.dumps(record, indent=2))
    return {k: v for k, v in record.items() if k not in ("examples", "selected")}


def sync_reviews(output: Path, stash: Stash):
    record = json.loads((output / "calibration.json").read_text())
    native = {
        e["id"]: e
        for mid in (record["model_id"], record["test_review_model_id"])
        for e in stash.call("GET", f"/intuitions/{mid}/examples")
    }
    reviewed = []
    for example in record["examples"]:
        current = native[example["native_id"]]
        reviewed.append(
            {
                **example,
                "label": current["label"],
                "needs_review": current["needs_review"],
                "human_reviewed": not current["needs_review"]
                if record.get("label_policy") != "automatic_exploratory"
                else example.get("human_reviewed", False),
                "review_note": current["note"],
                "preference": example["preference"]
                if current["label"] == example["label"]
                else current["note"]
                or "Reviewer changed this label; do not infer a style rule from the original feedback.",
            }
        )
    (output / "reviewed.jsonl").write_text("".join(json.dumps(e) + "\n" for e in reviewed))
    return {
        "reviewed": sum(not e["needs_review"] for e in reviewed),
        "pending": sum(e["needs_review"] for e in reviewed),
    }
