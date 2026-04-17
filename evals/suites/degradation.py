"""Degradation evaluation suite — stress-tests the memory pipeline under scale,
temporal pressure, and content bloat.

Three test categories:
  1. Scale degradation:     NDCG@5 at increasing notebook sizes (10→1000 pages)
  2. Temporal suppression:  critical pages survive N injection rounds
  3. Near-duplicate:        newest version of a page outranks stale duplicates
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import asyncpg

from evals.config import DATASETS_DIR, cfg
from evals.db import truncate_all
from evals.harness import (
    EvalResult,
    bulk_insert_pages,
    insert_page,
    make_persona,
    run_injection_loop,
)
from evals.judges.metrics import compute_retrieval_metrics

_SCENARIOS_FILE = DATASETS_DIR / "degradation_scenarios.jsonl"


def _load_scenarios(path: Path = _SCENARIOS_FILE) -> list[dict]:
    with open(path) as f:
        return [json.loads(line.strip()) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

class DegradationSuite:
    """Evaluates retrieval resilience under scale, temporal, and bloat stress."""

    name = "degradation"

    def __init__(self, scenarios_path: Path | None = None) -> None:
        self._path = scenarios_path or _SCENARIOS_FILE

    async def run(self, pool: asyncpg.Pool) -> list[EvalResult]:
        scenarios = _load_scenarios(self._path)
        results: list[EvalResult] = []

        for scenario in scenarios:
            stype = scenario.get("type")
            if stype == "scale":
                results += await self._run_scale(pool, scenario)
            elif stype == "temporal":
                results.append(await self._run_temporal(pool, scenario))
            elif stype == "duplicate":
                results.append(await self._run_duplicate(pool, scenario))
            await truncate_all(pool)

        return results

    # ------------------------------------------------------------------
    # 1. Scale degradation
    # ------------------------------------------------------------------

    async def _run_scale(
        self, pool: asyncpg.Pool, scenario: dict,
    ) -> list[EvalResult]:
        sid = scenario["id"]
        results: list[EvalResult] = []
        ndcg_values: dict[int, float] = {}

        for n_distractors in scenario.get("scale_levels", [10, 100, 500]):
            sub_sid = f"{sid}_n{n_distractors}"
            try:
                persona = await make_persona(pool)
                notebook_id = persona["notebook_id"]
                history_id = persona["history_id"]
                persona_id = persona["id"]

                target = scenario["target_page"]
                target_id = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=target["name"],
                    content=target["content"],
                    keywords=target.get("keywords", []),
                    persona_id=persona_id,
                )
                await bulk_insert_pages(
                    pool, notebook_id, persona_id, n=n_distractors,
                )

                from backend.services import injection_service

                result = await injection_service.compute_injection(
                    agent_id=persona_id,
                    notebook_id=notebook_id,
                    history_id=history_id,
                    prompt_text=scenario["query"],
                    session_state_data={
                        "prompt_num": 1,
                        "session_start": "2025-01-01T00:00:00",
                        "items": {},
                    },
                )

                injected = result.get("injected_items", [])
                retrieved_names = _extract_page_names(
                    pool, injected, {target["name"]: target_id},
                )
                relevant = [{"name": target["name"], "grade": 3}]
                metrics = compute_retrieval_metrics(retrieved_names, relevant)
                ndcg = metrics.get("NDCG@5", 0.0)
                ndcg_values[n_distractors] = ndcg

                passed = ndcg >= cfg.degradation_min_ndcg5
                metrics["n_distractors"] = float(n_distractors)
                results.append(EvalResult(
                    suite=self.name,
                    scenario_id=sub_sid,
                    description=f"{scenario['description']} (n={n_distractors})",
                    metrics=metrics,
                    passed=passed,
                    details={
                        "query": scenario["query"],
                        "target": target["name"],
                        "retrieved": retrieved_names,
                    },
                ))
            except Exception as exc:
                results.append(EvalResult(
                    suite=self.name, scenario_id=sub_sid,
                    description=f"{scenario['description']} (n={n_distractors})",
                    metrics={}, passed=False, error=str(exc),
                ))
            finally:
                await truncate_all(pool)

        if len(ndcg_values) >= 2:
            levels = sorted(ndcg_values)
            first, last = ndcg_values[levels[0]], ndcg_values[levels[-1]]
            drop = (first - last) / first if first > 0 else 0.0
            results.append(EvalResult(
                suite=self.name,
                scenario_id=f"{sid}_curve",
                description=f"{scenario['description']} — degradation curve",
                metrics={
                    "ndcg5_first": first,
                    "ndcg5_last": last,
                    "degradation_pct": drop,
                },
                passed=drop <= cfg.degradation_max_drop,
                details={"ndcg_by_scale": ndcg_values},
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Temporal suppression
    # ------------------------------------------------------------------

    async def _run_temporal(
        self, pool: asyncpg.Pool, scenario: dict,
    ) -> EvalResult:
        sid = scenario["id"]
        description = scenario.get("description", sid)
        try:
            persona = await make_persona(pool)
            notebook_id = persona["notebook_id"]
            history_id = persona["history_id"]
            persona_id = persona["id"]

            name_to_id: dict[str, uuid.UUID] = {}

            always_page = scenario.get("always_inject_page")
            if always_page:
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=always_page["name"],
                    content=always_page["content"],
                    keywords=always_page.get("keywords", []),
                    auto_inject=True,
                    persona_id=persona_id,
                )
                name_to_id[always_page["name"]] = pid

            target_page = scenario.get("target_page")
            if target_page:
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=target_page["name"],
                    content=target_page["content"],
                    keywords=target_page.get("keywords", []),
                    persona_id=persona_id,
                )
                name_to_id[target_page["name"]] = pid

            for dp in scenario.get("distractor_pages", []):
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=dp["name"],
                    content=dp["content"],
                    keywords=dp.get("keywords", []),
                    persona_id=persona_id,
                )
                name_to_id[dp["name"]] = pid

            rounds = scenario.get("rounds", 10)
            loop_results = await run_injection_loop(
                persona_id=persona_id,
                notebook_id=notebook_id,
                history_id=history_id,
                prompt_text=scenario["query"],
                rounds=rounds,
            )

            id_to_name = {str(v): k for k, v in name_to_id.items()}

            if always_page:
                always_name = always_page["name"]
                appearances = 0
                for r in loop_results:
                    names = _extract_names_from_result(r, id_to_name)
                    if always_name in names:
                        appearances += 1
                survival_rate = appearances / rounds
                passed = survival_rate >= cfg.degradation_temporal_survival
                return EvalResult(
                    suite=self.name, scenario_id=sid, description=description,
                    metrics={
                        "survival_rate": survival_rate,
                        "appearances": float(appearances),
                        "rounds": float(rounds),
                    },
                    passed=passed,
                    details={"always_inject_page": always_name},
                )

            if target_page:
                target_name = target_page["name"]
                expect_fade = scenario.get("expect_fade", False)

                first_half = loop_results[: rounds // 2]
                second_half = loop_results[rounds // 2 :]

                first_count = sum(
                    1 for r in first_half
                    if target_name in _extract_names_from_result(r, id_to_name)
                )
                second_count = sum(
                    1 for r in second_half
                    if target_name in _extract_names_from_result(r, id_to_name)
                )

                if expect_fade:
                    passed = second_count < first_count
                    return EvalResult(
                        suite=self.name, scenario_id=sid, description=description,
                        metrics={
                            "first_half_appearances": float(first_count),
                            "second_half_appearances": float(second_count),
                        },
                        passed=passed,
                    )

                last_result = loop_results[-1]
                last_names = _extract_names_from_result(last_result, id_to_name)
                reappeared = target_name in last_names
                ever_appeared = any(
                    target_name in _extract_names_from_result(r, id_to_name)
                    for r in loop_results
                )
                passed = ever_appeared
                return EvalResult(
                    suite=self.name, scenario_id=sid, description=description,
                    metrics={
                        "ever_appeared": float(ever_appeared),
                        "reappeared_final": float(reappeared),
                        "rounds": float(rounds),
                    },
                    passed=passed,
                )

            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={}, passed=False,
                error="Scenario has neither always_inject_page nor target_page",
            )

        except Exception as exc:
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={}, passed=False, error=str(exc),
            )

    # ------------------------------------------------------------------
    # 3. Near-duplicate disambiguation
    # ------------------------------------------------------------------

    async def _run_duplicate(
        self, pool: asyncpg.Pool, scenario: dict,
    ) -> EvalResult:
        sid = scenario["id"]
        description = scenario.get("description", sid)
        try:
            persona = await make_persona(pool)
            notebook_id = persona["notebook_id"]
            history_id = persona["history_id"]
            persona_id = persona["id"]

            name_to_id: dict[str, uuid.UUID] = {}
            current_name: str | None = None

            for version in scenario["versions"]:
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=version["name"],
                    content=version["content"],
                    keywords=version.get("keywords", []),
                    persona_id=persona_id,
                )
                name_to_id[version["name"]] = pid
                if version.get("is_current"):
                    current_name = version["name"]

            from backend.services import injection_service

            result = await injection_service.compute_injection(
                agent_id=persona_id,
                notebook_id=notebook_id,
                history_id=history_id,
                prompt_text=scenario["query"],
                session_state_data={
                    "prompt_num": 1,
                    "session_start": "2025-01-01T00:00:00",
                    "items": {},
                },
            )

            injected = result.get("injected_items", [])
            id_to_name = {str(v): k for k, v in name_to_id.items()}
            retrieved_names = _extract_names_from_result(result, id_to_name)

            current_in_results = current_name in retrieved_names if current_name else False
            current_rank = (
                retrieved_names.index(current_name) + 1
                if current_in_results else len(retrieved_names) + 1
            )
            total_versions = len(scenario["versions"])

            passed = current_in_results and current_rank <= 2
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={
                    "current_retrieved": float(current_in_results),
                    "current_rank": float(current_rank),
                    "versions_retrieved": float(
                        sum(1 for n in retrieved_names if n in name_to_id)
                    ),
                    "total_versions": float(total_versions),
                },
                passed=passed,
                details={
                    "query": scenario["query"],
                    "current_version": current_name,
                    "retrieved_order": retrieved_names,
                },
            )

        except Exception as exc:
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={}, passed=False, error=str(exc),
            )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, float]:
        scale_results = [r for r in results if "n_distractors" in r.metrics]
        temporal_results = [r for r in results if "survival_rate" in r.metrics or "ever_appeared" in r.metrics]
        dup_results = [r for r in results if "current_rank" in r.metrics]
        curve_results = [r for r in results if "degradation_pct" in r.metrics]

        def _avg(rs: list[EvalResult], key: str) -> float:
            vals = [r.metrics[key] for r in rs if key in r.metrics]
            return sum(vals) / len(vals) if vals else 0.0

        agg: dict[str, float] = {
            "pass_rate": (
                sum(1 for r in results if r.passed) / len(results)
                if results else 0.0
            ),
        }
        if scale_results:
            agg["avg_scale_ndcg5"] = _avg(scale_results, "NDCG@5")
        if temporal_results:
            agg["temporal_pass_rate"] = (
                sum(1 for r in temporal_results if r.passed) / len(temporal_results)
            )
        if dup_results:
            agg["avg_current_rank"] = _avg(dup_results, "current_rank")
            agg["dup_pass_rate"] = (
                sum(1 for r in dup_results if r.passed) / len(dup_results)
            )
        if curve_results:
            agg["max_degradation_pct"] = max(
                r.metrics.get("degradation_pct", 0) for r in curve_results
            )
        return agg

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return aggregate.get("pass_rate", 0) >= 0.60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_page_names(
    pool: asyncpg.Pool,
    injected_items: list[dict],
    name_to_id: dict[str, uuid.UUID],
) -> list[str]:
    id_to_name = {str(v): k for k, v in name_to_id.items()}
    names: list[str] = []
    for item in injected_items:
        key = item.get("key", "")
        if key.startswith("page:"):
            page_uuid = key.split(":", 1)[1]
            name = id_to_name.get(page_uuid)
            if name:
                names.append(name)
    return names


def _extract_names_from_result(
    result: dict, id_to_name: dict[str, str],
) -> list[str]:
    names: list[str] = []
    for item in result.get("injected_items", []):
        key = item.get("key", "")
        if key.startswith("page:"):
            page_uuid = key.split(":", 1)[1]
            name = id_to_name.get(page_uuid)
            if name:
                names.append(name)
    return names
