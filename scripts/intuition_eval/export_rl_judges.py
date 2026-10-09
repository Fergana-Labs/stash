"""Fit the three GSM8K judges on all non-design rows and export them for the RL runs.

    python -m scripts.intuition_eval.export_rl_judges
"""

import asyncio
import json

from backend.config import settings

from . import tasks as T
from .jevcache import Grader
from .run import RUBRICS, Featurizer, drafted_rubric, fit_head, manipulation_question


async def main() -> None:
    task = T.gsm8k()
    grader = Grader(task.description, task.output_type, task.seeds)
    fz = Featurizer(grader)
    rubric = await drafted_rubric(task)
    full = [*rubric, task.raw_question]
    repair_q = await manipulation_question(task, full, [])
    full_q = [*full, repair_q]
    rows = task.rows + task.design
    repair = [task.attack(r, p) for fam in task.repair_families for p in task.families[fam]
              for r in rows if task.should_lose(r)]
    await fz.prepare(full_q, rows + repair)

    def fitted(questions, data):
        feats = [x for x in (fz.row(questions, r) for r in data) if x]
        return fit_head(task, questions, feats, dropout=False, seed=0)

    config = {
        "description": task.description,
        "jev_model": settings.JEV_MODEL,
        "judges": {
            "raw": {"questions": [task.raw_question], "head": None},
            "rubric": {"questions": rubric, "head": fitted(rubric, rows)},
            "robust": {"questions": full_q, "head": fitted(full_q, rows + repair)},
        },
    }
    path = RUBRICS / "gsm8k_rl_judges.json"
    path.write_text(json.dumps(config, indent=1) + "\n")
    print("wrote", path, {k: len(v["questions"]) for k, v in config["judges"].items()})


if __name__ == "__main__":
    asyncio.run(main())
