"""Jev answers for offline evaluation, cached on disk with the product's cache keys.

Uses backend.services.intuition.providers directly (no database), so an
evaluated rubric is asked exactly the way the product asks it.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
from pathlib import Path

from backend.config import settings
from backend.services.intuition import providers

CACHE = Path(__file__).parent / "data" / "jev_cache.jsonl"


class Grader:
    def __init__(self, description: str, output_type: str, seeds: list[dict] | None = None):
        self.version = {
            "provider": "jev",
            "provider_model": settings.JEV_MODEL,
            "description": description,
            "output_type": output_type,
        }
        self.seeds = seeds or []
        self.cache: dict[str, dict] = {}
        if CACHE.exists():
            for line in CACHE.read_text().splitlines():
                row = json.loads(line)
                self.cache[row["k"]] = row["a"]
        self.calls = 0
        self.failures = 0

    def key(self, question: dict, item) -> str:
        return providers.grade_key(providers.question_context(self.version, question, self.seeds), item)

    async def answers(self, rubric: list[dict], items: list) -> list[dict | None]:
        """Per item, {question_id: answer} for every rubric question (None if Jev failed)."""
        jobs = []
        for item in items:
            missing = [q for q in rubric if self.key(q, item) not in self.cache]
            if missing:
                jobs.append((self.version, missing, self.seeds, item))
        # Deduplicate identical items.
        unique = {json.dumps([j[3], [q["id"] for q in j[1]]], sort_keys=True): j for j in jobs}
        jobs = list(unique.values())
        for start in range(0, len(jobs), 48):
            batch = jobs[start : start + 48]
            results = await providers.grade_many(batch)
            lines = []
            for (_v, questions, _s, item), result in zip(batch, results):
                self.calls += 1
                if isinstance(result, providers.ProviderError):
                    self.failures += 1
                    continue
                for q in questions:
                    k = self.key(q, item)
                    self.cache[k] = result[q["id"]]
                    lines.append(json.dumps({"k": k, "a": result[q["id"]]}))
            with CACHE.open("a") as handle:
                # Several evaluation processes share this file; lock so lines never interleave.
                fcntl.flock(handle, fcntl.LOCK_EX)
                handle.write("".join(line + "\n" for line in lines))
                handle.flush()
                fcntl.flock(handle, fcntl.LOCK_UN)
            if start + 48 < len(jobs):
                print(f"  graded {start + len(batch)}/{len(jobs)}", flush=True)
        out = []
        for item in items:
            keys = [self.key(q, item) for q in rubric]
            out.append({q["id"]: self.cache[k] for q, k in zip(rubric, keys)} if all(k in self.cache for k in keys) else None)
        return out


def run(coro):
    return asyncio.run(coro)
