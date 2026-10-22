"""Fresh, unlabeled development/test designs. These are not Qwen comparison results.

Only Henry supplies their labels. They never enter training references,
criterion discovery, skill synthesis, GEPA, or generator post-training.
"""

from __future__ import annotations

import json
from pathlib import Path

from .corpus import digest
from .protocol import SYSTEM
from .runtime import html_only, render

CASES = [
    (
        "recipe-library",
        "A recipe library showing recipes, preparation times, collections, and saved notes.",
        "Use a compact, restrained editorial design with a narrow navigation sidebar and clear rows.",
    ),
    (
        "workshop-schedule",
        "A workshop scheduling workspace showing attendees, upcoming sessions, instructors, and room assignments.",
        "Use spacious pastel cards, large rounded controls, and decorative gradients.",
    ),
    (
        "photo-archive",
        "A photography archive homepage with projects, dates, categories, and contact information.",
        "Use a typographic, black-and-white editorial design with one restrained accent.",
    ),
    (
        "community-grants",
        "A grant application review dashboard showing applicants, funding amounts, review stages, and deadlines.",
        "Use a colorful card-heavy design with generous padding, friendly oversized typography, and multiple prominent calls to action.",
    ),
    (
        "equipment-log",
        "An equipment maintenance log showing assets, recent inspections, owners, and upcoming service dates.",
        "Use a dense professional table layout with subtle separators, readable labels, and compact actions.",
    ),
    (
        "music-lessons",
        "A landing page for independent music teachers to organize lessons, students, and practice plans.",
        "Use an airy expressive marketing design with large display typography and warm colors.",
    ),
]


def prepare(output: Path, stash, *, model: str):
    from anthropic import Anthropic

    if (output / "experiment.json").exists():
        raise ValueError("Do not add calibration data after the experiment has been frozen")
    file = output / "calibration.json"
    calibration = json.loads(file.read_text())
    client = Anthropic()
    directory = output / "classifier-test-candidates"
    directory.mkdir(exist_ok=True)
    for index, (name, brief, style) in enumerate(CASES):
        partition = "dev" if index < 2 else "test"
        record_id = "classifier-test:" + name
        if any(e["id"] == record_id for e in calibration["examples"]):
            continue
        html, png, generation = (
            directory / (name + ".html"),
            directory / (name + ".png"),
            directory / (name + ".generation.json"),
        )
        if not generation.exists():
            reply = client.messages.create(
                model=model,
                max_tokens=6000,
                system=SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": brief
                        + "\n"
                        + style
                        + "\nKeep the complete HTML source under 1800 tokens. Use a single viewport composition with concise CSS, no comments, and no inline SVG paths.",
                    }
                ],
            )
            if reply.stop_reason != "end_turn":
                generation.with_suffix(".truncated.json").write_text(
                    json.dumps(reply.model_dump(), indent=2)
                )
                raise ValueError("Classifier-test candidate was truncated")
            text = "".join(p.text for p in reply.content if p.type == "text")
            generation.write_text(
                json.dumps(
                    {
                        "model": model,
                        "text": text,
                        "brief": brief,
                        "style_prompt": style,
                        "label": None,
                        "purpose": f"classifier-{partition}-only",
                    },
                    indent=2,
                )
            )
        html.write_text(html_only(json.loads(generation.read_text())["text"]))
        if not png.exists():
            render(html, png)
        item = {"kind": "website", "brief": brief, "render": stash.image(png)}
        native_model = (
            calibration["model_id"] if partition == "dev" else calibration["test_review_model_id"]
        )
        native = stash.call(
            "POST",
            f"/intuitions/{native_model}/examples",
            json={
                "examples": [
                    {
                        "item": item,
                        "split": "eval",
                        "needs_review": True,
                        "note": f"Fresh classifier-{partition} design. No label is inferred. Choose whether you would keep this design as a visual reference. This is not a Qwen experiment result.",
                    }
                ]
            },
        )
        calibration["examples"].append(
            {
                "id": record_id,
                "session_id": None,
                "group": "new-classifier-test:" + name,
                "partition": partition,
                "split": "eval",
                "label": None,
                "quote": "",
                "preference": "",
                "needs_review": True,
                "sha256": digest(png.read_bytes()),
                "item": item,
                "file": str(png),
                "generation_model": model,
                "source": "generated_unlabeled_calibration_candidate",
                "native_id": native[0]["id"],
                "native_model_id": native_model,
            }
        )
        file.write_text(json.dumps(calibration, indent=2))
        print(json.dumps({"phase": "classifier-test", "prepared": name, "label": None}), flush=True)
    return {
        "fresh_unlabeled_test_designs": len(CASES),
        "labels_inferred": False,
        "generation_model": model,
    }
