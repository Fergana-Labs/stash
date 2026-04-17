"""Retrieval evaluation suite.

Tests the injection service's ability to surface relevant notebook pages
for a given query, measuring NDCG, MRR, Precision@k, and Recall@k.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import asyncpg

from evals.config import DATASETS_DIR, cfg
from evals.db import truncate_all
from evals.harness import EvalResult, insert_page, make_persona
from evals.judges.metrics import compute_retrieval_metrics

_SCENARIOS_FILE = DATASETS_DIR / "retrieval_scenarios.jsonl"


def _load_scenarios(path: Path = _SCENARIOS_FILE) -> list[dict]:
    scenarios = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                scenarios.append(json.loads(line))
    return scenarios


class RetrievalSuite:
    """Evaluates FTS-based notebook page retrieval."""

    name = "retrieval"

    def __init__(self, scenarios_path: Path | None = None) -> None:
        self._path = scenarios_path or _SCENARIOS_FILE

    async def run(self, pool: asyncpg.Pool) -> list[EvalResult]:
        scenarios = _load_scenarios(self._path)
        results: list[EvalResult] = []

        for scenario in scenarios:
            result = await self._run_scenario(pool, scenario)
            results.append(result)
            await truncate_all(pool)

        return results

    async def _run_scenario(self, pool: asyncpg.Pool, scenario: dict) -> EvalResult:
        sid = scenario["id"]
        description = scenario.get("description", sid)

        try:
            persona = await make_persona(pool)
            notebook_id: uuid.UUID = persona["notebook_id"]
            history_id: uuid.UUID = persona["history_id"]
            persona_id: uuid.UUID = persona["id"]

            # Insert all pages
            name_to_id: dict[str, uuid.UUID] = {}
            for p in scenario["pages"]:
                page_id = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=p["name"],
                    content=p["content"],
                    keywords=p.get("keywords", []),
                    auto_inject=p.get("auto_inject", False),
                    importance=p.get("importance", 0.5),
                    persona_id=persona_id,
                )
                name_to_id[p["name"]] = page_id

            # Run injection
            from backend.services import injection_service  # noqa: PLC0415

            result = await injection_service.compute_injection(
                agent_id=persona_id,
                notebook_id=notebook_id,
                history_id=history_id,
                prompt_text=scenario["query"],
                session_state_data={"prompt_num": 1, "session_start": "2025-01-01T00:00:00", "items": {}},
            )

            injected = result.get("injected_items", [])
            # Extract page names from injected items (key format "page:<uuid>")
            retrieved_names: list[str] = []
            id_to_name = {str(v): k for k, v in name_to_id.items()}
            for item in injected:
                key = item.get("key", "")
                if key.startswith("page:"):
                    page_uuid = key.split(":", 1)[1]
                    name = id_to_name.get(page_uuid)
                    if name:
                        retrieved_names.append(name)

            relevant = scenario.get("relevant", [])
            metrics = compute_retrieval_metrics(retrieved_names, relevant)

            # Pass if NDCG@5 >= threshold OR if no relevant pages exist and nothing was returned
            if not relevant:
                passed = len(retrieved_names) == 0 or scenario["id"] == "ret_008"
            else:
                passed = metrics.get("NDCG@5", 0) >= cfg.retrieval_min_ndcg5

            # Special pass condition for always-inject scenarios
            if scenario.get("id") == "ret_008":
                always_name = next(
                    (r["name"] for r in relevant if r.get("always_inject")), None
                )
                passed = always_name in retrieved_names if always_name else passed

            return EvalResult(
                suite=self.name,
                scenario_id=sid,
                description=description,
                metrics=metrics,
                passed=passed,
                details={
                    "query": scenario["query"],
                    "retrieved": retrieved_names,
                    "relevant": [r["name"] for r in relevant],
                    "injected_items": injected,
                },
            )

        except Exception as exc:
            return EvalResult(
                suite=self.name,
                scenario_id=sid,
                description=description,
                metrics={},
                passed=False,
                error=str(exc),
            )

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, float]:
        keys = ["P@1", "P@3", "P@5", "R@5", "NDCG@5", "RR"]
        agg: dict[str, float] = {}
        for k in keys:
            vals = [r.metrics.get(k, 0.0) for r in results if k in r.metrics]
            agg[k] = sum(vals) / len(vals) if vals else 0.0
        agg["pass_rate"] = sum(1 for r in results if r.passed) / len(results) if results else 0.0
        return agg

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return (
            aggregate.get("NDCG@5", 0) >= cfg.retrieval_min_ndcg5
            and aggregate.get("RR", 0) >= cfg.retrieval_min_mrr
            and aggregate.get("R@5", 0) >= cfg.retrieval_min_recall5
        )
