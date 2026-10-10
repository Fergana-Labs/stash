"""Bundled demo: a support-reply reviewer with real, pre-recorded judge answers.

demo_support_replies.json holds the spec and labeled examples (hand-written).
demo_support_replies.answers.json holds the judge's answers to every rubric
question for every item, recorded once with

    python -m backend.services.intuition.demo record

so loading the demo makes no provider calls. The loader replays the normal
workflow -- create, label, choose seeds, grade, fit, promote v1, add a rubric
question, refit, gate -- so the version history is real, not fabricated.
New predictions on new items still call the configured judge.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID

from ...config import settings
from ...database import get_pool
from . import providers, service

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "demo_support_replies.json"
ANSWERS_PATH = HERE / "demo_support_replies.answers.json"


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def _item(e: dict) -> dict:
    return {"customer": e["customer"], "reply": e["reply"]}


def _marker(item) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()


def _full_rubric(spec: dict) -> list[dict]:
    return [*spec["rubric_v1"], spec["added_in_v2"]]


async def record() -> None:
    """Grade every demo item with the current default judge and save the answers."""
    spec = _spec()
    provider, provider_model = "jev", settings.JEV_MODEL
    version = {
        "output_type": spec["output_type"],
        "description": spec["description"],
        "provider": provider,
        "provider_model": provider_model,
    }
    seeds = [
        {
            "kind": "item",
            "item": _item(spec["examples"][i]),
            "item_b": None,
            "label": spec["examples"][i]["label"],
        }
        for i in spec["seed_indexes"]
    ]
    items = [_item(e) for e in spec["examples"]] + [_item(e) for e in spec["inbox"]]
    rubric = _full_rubric(spec)
    results = await providers.grade_many([(version, rubric, seeds, item) for item in items])
    failures = [r for r in results if isinstance(r, providers.ProviderError)]
    if failures:
        raise SystemExit(f"{len(failures)} items failed to grade: {failures[0]}")
    ANSWERS_PATH.write_text(
        json.dumps(
            {
                "provider": provider,
                "provider_model": provider_model,
                "answers": {_marker(item): answers for item, answers in zip(items, results)},
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"Recorded {len(items)} items with {provider}/{provider_model} -> {ANSWERS_PATH.name}")


async def _insert_grades(model_id: UUID, recorded: dict, items: list) -> None:
    detail_row = await get_pool().fetchrow(
        "SELECT draft_version_id FROM intuition_models WHERE id = $1", model_id
    )
    version = await service._load_version(detail_row["draft_version_id"])
    version = {**version, "rubric": _full_rubric(_spec())}
    seeds = await service._seeds(version)
    for item in items:
        await service._store_answers(
            model_id, version, seeds, item, recorded["answers"][_marker(item)]
        )


async def load(owner_id: UUID) -> dict:
    spec = _spec()
    recorded = json.loads(ANSWERS_PATH.read_text())
    created = await service.create_model(
        owner_id,
        name=spec["name"],
        output_type=spec["output_type"],
        description=spec["description"],
        labels=spec["labels"],
        rubric=spec["rubric_v1"],
    )
    model_id = created["model"]["id"]
    await get_pool().execute(
        "UPDATE intuition_versions SET provider_model = $2 WHERE id = $1",
        created["draft"]["id"],
        recorded["provider_model"],
    )
    examples = await service.add_examples(
        owner_id,
        model_id,
        [{"item": _item(e), "label": e["label"], "split": e["split"]} for e in spec["examples"]],
        "human",
    )
    await service.update_draft(
        owner_id, model_id, {"seed_example_ids": [examples[i]["id"] for i in spec["seed_indexes"]]}
    )
    items = [_item(e) for e in spec["examples"]] + [_item(e) for e in spec["inbox"]]
    await _insert_grades(model_id, recorded, items)

    # v1: the original rubric.
    await service.fit(owner_id, model_id)
    await service.promote(owner_id, model_id)
    # v2: the reviewer noticed risky promises slipping through and added a question.
    await service.ensure_draft(owner_id, model_id)
    await service.update_draft(owner_id, model_id, {"rubric": _full_rubric(spec)})
    refit = await service.fit(owner_id, model_id)
    if refit["gate"]["passed"]:
        await service.promote(owner_id, model_id)

    # Calls from the support agent waiting in the review inbox.
    for e in spec["inbox"]:
        await service.predict(owner_id, model_id, _item(e), caller="support-agent")
    return await service.get_detail(owner_id, model_id)


if __name__ == "__main__":
    if sys.argv[1:] != ["record"]:
        raise SystemExit("usage: python -m backend.services.intuition.demo record")
    asyncio.run(record())
