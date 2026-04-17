"""Knowledge graph relations evaluation suite.

Tests:
1. Upsert creates correct relations
2. get_page_neighbors returns the right neighbours
3. Confidence filtering works
4. Relation invalidation (valid_until) works on conflict
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg

from evals.config import DATASETS_DIR, cfg
from evals.db import truncate_all
from evals.harness import EvalResult, insert_page, make_persona

_SCENARIOS_FILE = DATASETS_DIR / "kg_scenarios.jsonl"


def _load_scenarios(path: Path = _SCENARIOS_FILE) -> list[dict]:
    with open(path) as f:
        return [json.loads(l.strip()) for l in f if l.strip()]


class KGRelationsSuite:
    """Evaluates knowledge graph relation correctness and retrieval."""

    name = "kg_relations"

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
            from backend.services import notebook_service  # noqa: PLC0415

            persona = await make_persona(pool)
            notebook_id = persona["notebook_id"]
            persona_id = persona["id"]

            name_to_id: dict[str, object] = {}
            for p in scenario["pages"]:
                pid = await insert_page(
                    pool,
                    notebook_id=notebook_id,
                    name=p["name"],
                    content=p["content"],
                    persona_id=persona_id,
                )
                name_to_id[p["name"]] = pid

            # ── Scenario kg_007: confidence threshold ──────────────────────
            if scenario.get("id") == "kg_007":
                rel = scenario["relations"][0]
                await notebook_service.upsert_relation(
                    source_page_id=name_to_id[rel["source"]],
                    relation_type=rel["relation_type"],
                    target_page_id=name_to_id[rel["target"]],
                    confidence=rel.get("confidence", 0.4),
                )
                threshold = scenario.get("confidence_threshold", 0.6)
                neighbors = await _get_neighbors_above_threshold(
                    pool, notebook_id, name_to_id[rel["source"]], threshold
                )
                expect_retrieved = scenario.get("expect_neighbor_retrieved", False)
                retrieved_names = [n["name"] for n in neighbors]
                passed = (rel["target"] in retrieved_names) == expect_retrieved
                return EvalResult(
                    suite=self.name,
                    scenario_id=sid,
                    description=description,
                    metrics={"confidence_filter_correct": float(passed)},
                    passed=passed,
                    details={"neighbors": retrieved_names, "threshold": threshold},
                )

            # ── Scenario kg_008: relation invalidation ─────────────────────
            if scenario.get("verify_invalidation"):
                rel = scenario["relations"][0]
                then = rel["then_supersede_with"]

                # Insert original relation
                await notebook_service.upsert_relation(
                    source_page_id=name_to_id[rel["source"]],
                    relation_type=rel["relation_type"],
                    target_page_id=name_to_id[rel["target"]],
                    confidence=rel.get("confidence", 0.9),
                )
                # Supersede with new relation
                await notebook_service.upsert_relation(
                    source_page_id=name_to_id[rel["source"]],
                    relation_type=rel["relation_type"],
                    target_page_id=name_to_id[then["target"]],
                    confidence=then.get("confidence", 0.95),
                )
                await notebook_service.invalidate_conflicting_relations(
                    source_page_id=name_to_id[rel["source"]],
                    relation_type=rel["relation_type"],
                    new_target_page_id=name_to_id[then["target"]],
                )

                # Old relation should be invalidated (valid_until IS NOT NULL)
                old_row = await pool.fetchrow(
                    """
                    SELECT valid_until FROM page_relations
                    WHERE source_page_id = $1 AND relation_type = $2 AND target_page_id = $3
                    """,
                    name_to_id[rel["source"]],
                    rel["relation_type"],
                    name_to_id[rel["target"]],
                )
                old_invalidated = old_row is not None and old_row["valid_until"] is not None

                # New relation should be active (valid_until IS NULL)
                new_row = await pool.fetchrow(
                    """
                    SELECT valid_until FROM page_relations
                    WHERE source_page_id = $1 AND relation_type = $2 AND target_page_id = $3
                      AND valid_until IS NULL
                    """,
                    name_to_id[rel["source"]],
                    rel["relation_type"],
                    name_to_id[then["target"]],
                )
                new_active = new_row is not None
                passed = old_invalidated and new_active

                return EvalResult(
                    suite=self.name,
                    scenario_id=sid,
                    description=description,
                    metrics={
                        "old_invalidated": float(old_invalidated),
                        "new_active": float(new_active),
                    },
                    passed=passed,
                )

            # ── Default: upsert relations and verify neighbors ─────────────
            expected_rels = scenario.get("relations", [])
            for rel in expected_rels:
                await notebook_service.upsert_relation(
                    source_page_id=name_to_id[rel["source"]],
                    relation_type=rel["relation_type"],
                    target_page_id=name_to_id[rel["target"]],
                    confidence=rel.get("confidence", rel.get("confidence_min", 0.8)),
                )

            # Verify each expected relation is retrievable
            precision_scores: list[float] = []
            recall_scores: list[float] = []

            for rel in expected_rels:
                source_id = name_to_id[rel["source"]]
                neighbors = await notebook_service.get_page_neighbors(
                    page_ids=[source_id], notebook_id=notebook_id
                )
                target_names = {n["name"] for n in neighbors}
                found = rel["target"] in target_names
                precision_scores.append(float(found))

                # Check confidence meets minimum
                if found and "confidence_min" in rel:
                    matching = next((n for n in neighbors if n["name"] == rel["target"]), None)
                    confidence_ok = (
                        matching and float(matching.get("confidence", 0)) >= rel["confidence_min"]
                    )
                    recall_scores.append(float(confidence_ok))
                else:
                    recall_scores.append(float(found))

            precision = sum(precision_scores) / len(precision_scores) if precision_scores else 1.0
            recall = sum(recall_scores) / len(recall_scores) if recall_scores else 1.0

            # Bidirectional check (kg_006)
            expected_neighbor = scenario.get("expected_neighbors")
            bidirectional_ok = True
            if expected_neighbor:
                page_id = name_to_id[expected_neighbor["page"]]
                neighbors = await notebook_service.get_page_neighbors(
                    page_ids=[page_id], notebook_id=notebook_id
                )
                incoming = [n for n in neighbors if n.get("direction") == "incoming"]
                bidirectional_ok = any(
                    n["name"] == expected_neighbor["from"] for n in incoming
                )

            passed = (
                precision >= cfg.kg_min_precision
                and recall >= cfg.kg_min_recall
                and bidirectional_ok
            )

            return EvalResult(
                suite=self.name,
                scenario_id=sid,
                description=description,
                metrics={
                    "precision": precision,
                    "recall": recall,
                    "bidirectional_ok": float(bidirectional_ok),
                },
                passed=passed,
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
        def avg(key: str) -> float:
            vals = [r.metrics[key] for r in results if key in r.metrics]
            return sum(vals) / len(vals) if vals else 0.0

        return {
            "precision": avg("precision"),
            "recall": avg("recall"),
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else 0.0,
        }

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return (
            aggregate.get("precision", 0) >= cfg.kg_min_precision
            and aggregate.get("recall", 0) >= cfg.kg_min_recall
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_neighbors_above_threshold(
    pool: asyncpg.Pool, notebook_id, source_id, threshold: float
) -> list[dict]:
    """Get neighbours with confidence >= threshold directly via SQL."""
    rows = await pool.fetch(
        """
        SELECT np.name, pr.confidence, pr.relation_type
        FROM page_relations pr
        JOIN notebook_pages np ON np.id = pr.target_page_id
        WHERE pr.source_page_id = $1
          AND pr.confidence >= $2
          AND pr.valid_until IS NULL
        """,
        source_id,
        threshold,
    )
    return [dict(r) for r in rows]
