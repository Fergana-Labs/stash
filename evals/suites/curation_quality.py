"""Curation quality evaluation suite — end-to-end sleep-agent-through-retrieval.

Tests the full pipeline:
  1. Feed history events to the sleep agent
  2. Let it curate freely (real or mocked LLM)
  3. Run retrieval queries against the notebook the sleep agent created
  4. Measure: did the agent create pages that are actually retrievable?

Two modes:
  fast (default)  — mocks _llm_curate with a plausible structured response,
                    tests that the executor + retrieval pipeline works E2E.
  llm             — uses a real LLM for curation then judges quality with
                    LLM-as-judge.  Enabled when config.run_llm_suites is True.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg

from evals.config import DATASETS_DIR, cfg
from evals.db import truncate_all
from evals.harness import EvalResult, insert_history_event, make_persona

_SCENARIOS_FILE = DATASETS_DIR / "curation_quality_scenarios.jsonl"


def _load_scenarios(path: Path = _SCENARIOS_FILE) -> list[dict]:
    with open(path) as f:
        return [json.loads(line.strip()) for line in f if line.strip()]


class CurationQualitySuite:
    """Evaluates whether sleep agent curation produces retrievable knowledge."""

    name = "curation_quality"

    def __init__(self, scenarios_path: Path | None = None) -> None:
        self._path = scenarios_path or _SCENARIOS_FILE

    async def run(self, pool: asyncpg.Pool) -> list[EvalResult]:
        scenarios = _load_scenarios(self._path)
        results: list[EvalResult] = []

        for scenario in scenarios:
            if cfg.run_llm_suites:
                result = await self._run_llm_scenario(pool, scenario)
            else:
                result = await self._run_mocked_scenario(pool, scenario)
            results.append(result)
            await truncate_all(pool)

        return results

    # ------------------------------------------------------------------
    # Fast path: mocked LLM curation → retrieval
    # ------------------------------------------------------------------

    async def _run_mocked_scenario(
        self, pool: asyncpg.Pool, scenario: dict,
    ) -> EvalResult:
        sid = scenario["id"]
        description = scenario.get("description", sid)

        try:
            from backend.services import sleep_service

            persona = await make_persona(pool)
            persona_id = persona["id"]
            history_id = persona["history_id"]
            notebook_id = persona["notebook_id"]

            for ev_text in scenario["history_events"]:
                await insert_history_event(pool, history_id, ev_text)

            mock_actions = _build_mock_curation(scenario)

            with patch.object(
                sleep_service, "_llm_curate",
                new=AsyncMock(return_value=mock_actions),
            ):
                with patch.object(
                    sleep_service, "_generate_monologue_text",
                    new=AsyncMock(return_value="Session monologue."),
                ):
                    await sleep_service.curate(persona_id)

            return await self._evaluate_retrieval(
                pool, scenario, persona_id, notebook_id, history_id,
            )

        except Exception as exc:
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={}, passed=False, error=str(exc),
            )

    # ------------------------------------------------------------------
    # LLM path: real curation → retrieval → LLM-as-judge
    # ------------------------------------------------------------------

    async def _run_llm_scenario(
        self, pool: asyncpg.Pool, scenario: dict,
    ) -> EvalResult:
        sid = scenario["id"]
        description = scenario.get("description", sid)

        try:
            from backend.services import sleep_service

            persona = await make_persona(pool)
            persona_id = persona["id"]
            history_id = persona["history_id"]
            notebook_id = persona["notebook_id"]

            for ev_text in scenario["history_events"]:
                await insert_history_event(pool, history_id, ev_text)

            with patch.object(
                sleep_service, "_generate_monologue_text",
                new=AsyncMock(return_value="Session monologue."),
            ):
                curation_result = await sleep_service.curate(persona_id)

            if curation_result.get("status") not in ("completed", "ok"):
                return EvalResult(
                    suite=self.name, scenario_id=sid, description=description,
                    metrics={}, passed=False,
                    error=f"Curation status: {curation_result.get('status')}",
                )

            retrieval_eval = await self._evaluate_retrieval(
                pool, scenario, persona_id, notebook_id, history_id,
            )

            pages = await pool.fetch(
                "SELECT name, content_markdown, metadata FROM notebook_pages "
                "WHERE notebook_id = $1",
                notebook_id,
            )
            page_list = [dict(p) for p in pages]
            curation_metrics = _assess_curation_structure(page_list, scenario)
            retrieval_eval.metrics.update(curation_metrics)

            if page_list:
                from evals.judges.llm_judge import judge_curation_quality

                events_text = scenario["history_events"]
                page_names = [p["name"] for p in page_list]
                page_contents = "\n\n".join(
                    f"## {p['name']}\n{p['content_markdown']}" for p in page_list
                )
                judge = await judge_curation_quality(
                    events_text, ", ".join(page_names), page_contents,
                )
                retrieval_eval.metrics["judge_quality"] = judge.score
                retrieval_eval.details["judge_reasoning"] = judge.reasoning

            return retrieval_eval

        except Exception as exc:
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={}, passed=False, error=str(exc),
            )

    # ------------------------------------------------------------------
    # Shared retrieval evaluation
    # ------------------------------------------------------------------

    async def _evaluate_retrieval(
        self,
        pool: asyncpg.Pool,
        scenario: dict,
        persona_id: uuid.UUID,
        notebook_id: uuid.UUID,
        history_id: uuid.UUID,
    ) -> EvalResult:
        from backend.services import injection_service

        sid = scenario["id"]
        description = scenario.get("description", sid)
        queries = scenario.get("retrieval_queries", [])

        if not queries:
            return EvalResult(
                suite=self.name, scenario_id=sid, description=description,
                metrics={"hit_rate": 0.0}, passed=False,
                error="No retrieval queries in scenario",
            )

        hits = 0
        total = len(queries)
        per_query: list[dict] = []

        for q in queries:
            result = await injection_service.compute_injection(
                agent_id=persona_id,
                notebook_id=notebook_id,
                history_id=history_id,
                prompt_text=q["query"],
                session_state_data={
                    "prompt_num": 1,
                    "session_start": "2025-01-01T00:00:00",
                    "items": {},
                },
            )
            context = result.get("context", "").lower()
            expected_kw = q.get("expected_keywords", [])

            matched_kw = [kw for kw in expected_kw if kw.lower() in context]
            kw_hit_rate = len(matched_kw) / len(expected_kw) if expected_kw else 0.0

            if kw_hit_rate >= 0.5:
                hits += 1

            per_query.append({
                "query": q["query"],
                "kw_hit_rate": kw_hit_rate,
                "matched": matched_kw,
                "missed": [kw for kw in expected_kw if kw.lower() not in context],
                "tokens_used": result.get("total_tokens_used", 0),
            })

        overall_hit_rate = hits / total

        return EvalResult(
            suite=self.name,
            scenario_id=sid,
            description=description,
            metrics={
                "retrieval_hit_rate": overall_hit_rate,
                "queries_passed": float(hits),
                "queries_total": float(total),
            },
            passed=overall_hit_rate >= cfg.curation_min_retrieval_hit_rate,
            details={"per_query": per_query},
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, float]:
        hit_rates = [
            r.metrics["retrieval_hit_rate"]
            for r in results if "retrieval_hit_rate" in r.metrics
        ]
        agg: dict[str, float] = {
            "avg_retrieval_hit_rate": (
                sum(hit_rates) / len(hit_rates) if hit_rates else 0.0
            ),
            "pass_rate": (
                sum(1 for r in results if r.passed) / len(results)
                if results else 0.0
            ),
        }

        judge_scores = [
            r.metrics["judge_quality"]
            for r in results if "judge_quality" in r.metrics
        ]
        if judge_scores:
            agg["avg_judge_quality"] = sum(judge_scores) / len(judge_scores)

        return agg

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return aggregate.get("avg_retrieval_hit_rate", 0) >= cfg.curation_min_retrieval_hit_rate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_mock_curation(scenario: dict) -> dict:
    """Build a plausible curation response from the scenario data.

    This produces create_notes actions with titles and keywords derived from
    the retrieval queries' expected keywords, simulating what a competent
    LLM curator would produce.
    """
    create_notes: list[dict] = []
    seen_topics: set[str] = set()

    for q in scenario.get("retrieval_queries", []):
        keywords = q.get("expected_keywords", [])
        title_words = [kw for kw in keywords[:3] if kw not in seen_topics]
        if not title_words:
            continue
        seen_topics.update(title_words)

        title = " ".join(title_words).title() + " Notes"
        content = f"Summary of {', '.join(keywords)}. "
        for ev in scenario["history_events"]:
            for kw in keywords:
                if kw.lower() in ev.lower():
                    content += f"{ev} "
                    break

        create_notes.append({
            "title": title,
            "content": content.strip(),
            "keywords": keywords,
            "importance": 0.7,
            "type": "note",
            "category": "Session Notes",
            "folder": "Session Notes",
        })

    return {
        "create_notes": create_notes,
        "update_notes": [],
        "merge_notes": [],
        "delete_notes": [],
        "update_categories": [],
        "extract_relations": [],
        "health": {},
    }


def _assess_curation_structure(pages: list[dict], scenario: dict) -> dict[str, float]:
    """Compute structural quality metrics for the curated notebook."""
    n_pages = len(pages)
    n_queries = len(scenario.get("retrieval_queries", []))

    all_keywords: set[str] = set()
    for p in pages:
        meta = p.get("metadata", {})
        if isinstance(meta, dict):
            all_keywords.update(kw.lower() for kw in meta.get("keywords", []))

    expected_kw: set[str] = set()
    for q in scenario.get("retrieval_queries", []):
        expected_kw.update(kw.lower() for kw in q.get("expected_keywords", []))

    kw_coverage = (
        len(all_keywords & expected_kw) / len(expected_kw)
        if expected_kw else 0.0
    )

    return {
        "pages_created": float(n_pages),
        "keyword_coverage": kw_coverage,
        "pages_per_query": n_pages / n_queries if n_queries else 0.0,
    }
