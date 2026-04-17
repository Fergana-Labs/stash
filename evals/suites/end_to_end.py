"""End-to-end task performance evaluation suite.

Measures whether the full injection pipeline surfaces the right context
for a given agent task, across FTS-only vs FTS+graph retrieval strategies.
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg

from evals.config import DATASETS_DIR, cfg
from evals.db import truncate_all
from evals.harness import EvalResult, insert_page, make_persona

_SCENARIOS_FILE = DATASETS_DIR / "task_scenarios.jsonl"


def _load_scenarios(path: Path = _SCENARIOS_FILE) -> list[dict]:
    with open(path) as f:
        return [json.loads(l.strip()) for l in f if l.strip()]


class EndToEndSuite:
    """Evaluates end-to-end memory injection for agent task completion."""

    name = "end_to_end"

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
            from backend.services import injection_service  # noqa: PLC0415

            persona = await make_persona(pool)
            notebook_id = persona["notebook_id"]
            history_id = persona["history_id"]
            persona_id = persona["id"]

            name_to_id = {}
            for p in scenario["pages"]:
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=p["name"],
                    content=p["content"],
                    keywords=p.get("keywords", []),
                    auto_inject=p.get("auto_inject", False),
                    persona_id=persona_id,
                )
                name_to_id[p["name"]] = pid

            result = await injection_service.compute_injection(
                agent_id=persona_id,
                notebook_id=notebook_id,
                history_id=history_id,
                prompt_text=scenario["task"],
                session_state_data={
                    "prompt_num": 1,
                    "session_start": "2025-01-01T00:00:00",
                    "items": {},
                },
            )

            injected = result.get("injected_items", [])
            id_to_name = {str(v): k for k, v in name_to_id.items()}
            retrieved_names: list[str] = []
            for item in injected:
                key = item.get("key", "")
                if key.startswith("page:"):
                    name = id_to_name.get(key.split(":", 1)[1])
                    if name:
                        retrieved_names.append(name)

            # Evaluate
            expected_pages = scenario.get("expected_pages")
            expected_page = scenario.get("expected_page")
            if expected_page:
                expected_pages = [expected_page]

            no_relevant = not expected_pages
            if no_relevant:
                # Empty injection or very low tokens — should not hallucinate context
                passed = result.get("total_tokens_used", 0) == 0 or len(retrieved_names) == 0
                hit_rate = 1.0 if passed else 0.0
            else:
                hits = [p for p in expected_pages if p in retrieved_names]
                hit_rate = len(hits) / len(expected_pages)
                passed = hit_rate >= cfg.e2e_min_hit_rate

            metrics = {
                "hit_rate": hit_rate,
                "num_injected": float(len(retrieved_names)),
                "tokens_used": float(result.get("total_tokens_used", 0)),
            }

            # Optional LLM judge
            if cfg.run_llm_suites and retrieved_names:
                from evals.judges.llm_judge import judge_context_usefulness  # noqa: PLC0415

                injected_page_dicts = [
                    {"name": n, "content": next(p["content"] for p in scenario["pages"] if p["name"] == n)}
                    for n in retrieved_names
                    if any(p["name"] == n for p in scenario["pages"])
                ]
                judge = await judge_context_usefulness(
                    task=scenario["task"],
                    injected_pages=injected_page_dicts,
                    expected_answer_hint=scenario.get("answer_hint", ""),
                )
                metrics["context_usefulness"] = judge.score
                passed = passed and judge.score >= 0.6

            return EvalResult(
                suite=self.name,
                scenario_id=sid,
                description=description,
                metrics=metrics,
                passed=passed,
                details={
                    "task": scenario["task"],
                    "expected": expected_pages,
                    "retrieved": retrieved_names,
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
        hit_rates = [r.metrics.get("hit_rate", 0.0) for r in results if "hit_rate" in r.metrics]
        avg_hr = sum(hit_rates) / len(hit_rates) if hit_rates else 0.0
        return {
            "avg_hit_rate": avg_hr,
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else 0.0,
        }

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return aggregate.get("avg_hit_rate", 0) >= cfg.e2e_min_hit_rate
