"""Bundled demos with real, pre-recorded judge answers.

  support-replies    demo_support_replies.json: a support lead's send/edit/rewrite
                     call on drafted replies (hand-written examples).
  web-agent-success  demo_web_agent.json: did a web agent actually finish the task?
                     (AgentRewardBench trajectories, split by provenance).

Each <name>.json holds the spec and labeled examples; <name>.answers.json holds
the judge's answers to every rubric question for every item, recorded once with

    python -m backend.services.intuition.demo record <slug>

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
DEMOS = {"support-replies": "demo_support_replies", "web-agent-success": "demo_web_agent"}


def _spec(slug: str) -> dict:
    return json.loads((HERE / f"{DEMOS[slug]}.json").read_text())


def _answers_path(slug: str) -> Path:
    return HERE / f"{DEMOS[slug]}.answers.json"


def catalog() -> list[dict]:
    out = []
    for slug in DEMOS:
        spec = _spec(slug)
        out.append(
            {
                "slug": slug,
                "name": spec["name"],
                "when_to_use": spec.get("when_to_use", ""),
                "output_type": spec["output_type"],
                "labels": [
                    {"id": label["id"], "flag": label.get("flag", False)}
                    for label in spec["labels"]
                ],
                "examples": len(spec["examples"]),
                "attribution": spec.get("attribution"),
            }
        )
    return out


def _item(e: dict):
    return e["item"] if "item" in e else {"customer": e["customer"], "reply": e["reply"]}


def _marker(item) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()


def _full_rubric(spec: dict) -> list[dict]:
    return [*spec["rubric_v1"], spec["added_in_v2"]]


async def record(slug: str) -> None:
    """Grade every demo item with the current default judge and save the answers."""
    spec = _spec(slug)
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
    answers_path = _answers_path(slug)
    results = await providers.grade_many([(version, rubric, seeds, item) for item in items])
    failures = [r for r in results if isinstance(r, providers.ProviderError)]
    if failures:
        raise SystemExit(f"{len(failures)} items failed to grade: {failures[0]}")
    answers_path.write_text(
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
    print(f"Recorded {len(items)} items with {provider}/{provider_model} -> {answers_path.name}")


async def _insert_grades(model_id: UUID, spec: dict, recorded: dict, items: list) -> None:
    detail_row = await get_pool().fetchrow(
        "SELECT draft_version_id FROM intuition_models WHERE id = $1", model_id
    )
    version = await service._load_version(detail_row["draft_version_id"])
    version = {**version, "rubric": _full_rubric(spec)}
    seeds = await service._seeds(version)
    for item in items:
        await service._store_answers(
            model_id, version, seeds, item, recorded["answers"][_marker(item)]
        )


async def load(owner_id: UUID, slug: str = "support-replies") -> dict:
    spec = _spec(slug)
    recorded = json.loads(_answers_path(slug).read_text())
    created = await service.create_model(
        owner_id,
        name=spec["name"],
        output_type=spec["output_type"],
        description=spec["description"],
        labels=spec["labels"],
        rubric=spec["rubric_v1"],
        when_to_use=spec.get("when_to_use", ""),
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
    await _insert_grades(model_id, spec, recorded, items)

    # v1: the original rubric.
    await service.fit(owner_id, model_id)
    await service.promote(owner_id, model_id)
    # v2: the reviewer noticed a failure mode slipping through and added a question.
    await service.ensure_draft(owner_id, model_id)
    await service.update_draft(owner_id, model_id, {"rubric": _full_rubric(spec)})
    refit = await service.fit(owner_id, model_id)
    if refit["gate"]["passed"]:
        await service.promote(owner_id, model_id)

    # Calls from the agent waiting in the review inbox.
    caller = "support-agent" if slug == "support-replies" else "web-agent"
    for e in spec["inbox"]:
        await service.predict(owner_id, model_id, _item(e), caller=caller)
    return await service.get_detail(owner_id, model_id)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "record" or sys.argv[2] not in DEMOS:
        raise SystemExit(
            f"usage: python -m backend.services.intuition.demo record {{{'|'.join(DEMOS)}}}"
        )
    asyncio.run(record(sys.argv[2]))
