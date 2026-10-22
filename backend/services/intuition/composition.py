"""Evals that use other evals: a dependency's decision becomes a rubric answer.

An `eval` question names another eval of the same owner. Its answer is that
eval's probabilities over its own decisions for the same item, so the parent's
head learns how much the dependency's verdict should move its own decision.

The dependency version is pinned on the question when the rubric is saved.
Because the question (with its pinned version) is part of every cached answer's
key, a later save of the dependency never silently changes the parent's
features; re-saving the parent's criteria re-pins to the dependency's newest
saved version. Cycles are rejected and depth is bounded.
"""

from __future__ import annotations

import re
from uuid import UUID

from ...database import get_pool
from . import providers, service

MAX_DEPTH = 3


def _slug(name: str) -> str:
    return ("eval_" + re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_-"))[:60] or "eval"


def _options(version: dict) -> dict[str, str]:
    if version["output_type"] == "multi":
        raise ValueError("Multi-issue evals cannot be used as a signal in another eval yet")
    if version["output_type"] == "choice":
        return {label["id"]: label["description"] or label["id"] for label in version["labels"]}
    return {"good": "The eval judged it good", "bad": "The eval judged it bad"}


async def _depends_on(version: dict, target: UUID, depth: int) -> bool:
    """True when `version` reaches `target` through its eval questions."""
    for q in version["rubric"]:
        if q["type"] != "eval":
            continue
        if UUID(q["eval_id"]) == target:
            return True
        if depth >= MAX_DEPTH:
            raise ValueError(f"Evals can be nested at most {MAX_DEPTH} levels deep")
        child = await service._load_version(UUID(q["version_id"]))
        if child is not None and await _depends_on(child, target, depth + 1):
            return True
    return False


async def resolve(owner_id: UUID, model_id: UUID | None, rubric: list[dict]) -> list[dict]:
    """Fill each eval question's options and pinned version; reject foreign or cyclic ones."""
    resolved = []
    for q in rubric:
        if not isinstance(q, dict) or q.get("type") != "eval":
            resolved.append(q)
            continue
        try:
            dependency_id = UUID(str(q.get("eval_id")))
        except ValueError as exc:
            raise ValueError("An eval question needs the id of the eval it uses") from exc
        if dependency_id == model_id:
            raise ValueError("An eval cannot use its own decision as a signal")
        try:
            dependency = await service._model(owner_id, dependency_id)
        except service.NotFound as exc:
            raise ValueError("The eval used as a signal was not found") from exc
        version_id = q.get("version_id") or dependency["active_version_id"]
        version = await service._load_version(UUID(str(version_id))) if version_id else None
        if version is None or version["model_id"] != dependency_id:
            raise ValueError(f"Save “{dependency['name']}” before using it as a signal")
        if version["head_stale"]:
            raise ValueError(f"“{dependency['name']}” v{version['number']} has no fitted head")
        if model_id is not None and await _depends_on(version, model_id, 1):
            raise ValueError(
                f"“{dependency['name']}” already uses this eval; that would be a cycle"
            )
        resolved.append(
            {
                "id": q.get("id") or _slug(dependency["name"]),
                "type": "eval",
                "prompt": q.get("prompt") or f"Decision of the “{dependency['name']}” eval",
                "criteria": _options(version),
                "eval_id": str(dependency_id),
                "version_id": str(version["id"]),
            }
        )
    return resolved


async def answer(version: dict, question: dict, item) -> dict:
    """The pinned dependency's decision probabilities for this item, as a rubric answer."""
    owner_id = await get_pool().fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id = $1", version["model_id"]
    )
    try:
        result = await service.predict(
            owner_id,
            UUID(question["eval_id"]),
            item,
            version_id=UUID(question["version_id"]),
            caller=f"eval:{version['model_id']}",
            log=False,
        )
    except (service.NotFound, service.Conflict) as exc:
        raise providers.ProviderError(
            f"The eval used by question {question['id']} is unavailable: {exc}"
        ) from exc
    probabilities = result["probabilities"]
    return providers._checked(
        {option: probabilities.get(option, 0.0) for option in question["criteria"]}, question
    )
