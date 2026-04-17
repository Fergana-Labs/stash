"""Sleep agent curation evaluation suite.

Two modes:
  fast (default)  — mocks the LLM; tests executor correctness (action application,
                    relation upsert, watermark advancement). No Anthropic calls.
  llm             — uses a real LLM call and judges output quality with LLM-as-judge.
                    Enabled when config.run_llm_suites is True.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import asyncpg

from evals.config import cfg
from evals.db import truncate_all
from evals.harness import EvalResult, insert_history_event, make_persona


class SleepAgentSuite:
    """Evaluates sleep agent action execution and (optionally) LLM curation quality."""

    name = "sleep_agent"

    async def run(self, pool: asyncpg.Pool) -> list[EvalResult]:
        results: list[EvalResult] = []

        # Fast (mocked) scenarios — always run
        results += await self._run_executor_scenarios(pool)

        # LLM quality scenarios — run only when enabled
        if cfg.run_llm_suites:
            results += await self._run_llm_quality_scenarios(pool)

        return results

    # ------------------------------------------------------------------
    # Fast scenarios (no LLM)
    # ------------------------------------------------------------------

    async def _run_executor_scenarios(self, pool: asyncpg.Pool) -> list[EvalResult]:
        results = []
        scenarios = [
            ("sa_exec_001", "create_notes action creates a page", self._scenario_create_notes),
            ("sa_exec_002", "update_notes action appends content", self._scenario_update_notes),
            ("sa_exec_003", "extract_relations action upserts a relation", self._scenario_extract_relations),
            ("sa_exec_004", "delete_notes action removes page", self._scenario_delete_notes),
            ("sa_exec_005", "watermark advances after events are processed", self._scenario_watermark),
        ]
        for sid, desc, fn in scenarios:
            result = await fn(pool, sid, desc)
            results.append(result)
            await truncate_all(pool)
        return results

    async def _scenario_create_notes(
        self, pool: asyncpg.Pool, sid: str, description: str
    ) -> EvalResult:
        from backend.services import sleep_service  # noqa: PLC0415

        persona = await make_persona(pool)
        persona_id, history_id, notebook_id = (
            persona["id"], persona["history_id"], persona["notebook_id"]
        )
        await insert_history_event(pool, history_id, "Implemented OAuth2 login flow")

        mock_actions = {
            "create_notes": [
                {
                    "name": "OAuth2 Implementation",
                    "content": "Implemented the OAuth2 login flow. Covers authorization code grant.",
                    "note_type": "summary",
                    "keywords": ["oauth2", "login", "auth"],
                    "importance": 0.8,
                }
            ],
            "update_notes": [], "merge_notes": [], "delete_notes": [],
            "update_categories": [], "extract_relations": [], "health": {},
        }

        with patch.object(sleep_service, "_llm_curate", new=AsyncMock(return_value=mock_actions)):
            with patch.object(sleep_service, "_generate_monologue_text", new=AsyncMock(return_value="Session monologue.")):
                await sleep_service.curate(persona_id)

        page = await pool.fetchrow(
            "SELECT id, name, content_markdown FROM notebook_pages WHERE notebook_id = $1",
            notebook_id,
        )
        created = page is not None and page["name"] == "OAuth2 Implementation"
        return EvalResult(
            suite=self.name, scenario_id=sid, description=description,
            metrics={"page_created": float(created)},
            passed=created,
        )

    async def _scenario_update_notes(
        self, pool: asyncpg.Pool, sid: str, description: str
    ) -> EvalResult:
        from backend.services import sleep_service  # noqa: PLC0415

        persona = await make_persona(pool)
        persona_id, history_id, notebook_id = (
            persona["id"], persona["history_id"], persona["notebook_id"]
        )

        # Pre-create the page
        page_id = await insert_page_via_service(
            pool, notebook_id, persona_id,
            name="API design notes",
            content="Initial content: REST endpoints designed.",
        )
        await insert_history_event(pool, history_id, "Added pagination to the list endpoint")

        mock_actions = {
            "create_notes": [],
            "update_notes": [
                {"id": str(page_id), "content": "\n\nAdded cursor-based pagination to GET /items."}
            ],
            "merge_notes": [], "delete_notes": [], "update_categories": [],
            "extract_relations": [], "health": {},
        }

        with patch.object(sleep_service, "_llm_curate", new=AsyncMock(return_value=mock_actions)):
            with patch.object(sleep_service, "_generate_monologue_text", new=AsyncMock(return_value="Updated pagination.")):
                await sleep_service.curate(persona_id)

        page = await pool.fetchrow(
            "SELECT content_markdown FROM notebook_pages WHERE id = $1", page_id
        )
        updated = page is not None and "pagination" in page["content_markdown"].lower()
        return EvalResult(
            suite=self.name, scenario_id=sid, description=description,
            metrics={"page_updated": float(updated)},
            passed=updated,
        )

    async def _scenario_extract_relations(
        self, pool: asyncpg.Pool, sid: str, description: str
    ) -> EvalResult:
        from backend.services import sleep_service  # noqa: PLC0415

        persona = await make_persona(pool)
        persona_id, history_id, notebook_id = (
            persona["id"], persona["history_id"], persona["notebook_id"]
        )

        await insert_page_via_service(pool, notebook_id, persona_id, "FastAPI", "FastAPI framework")
        await insert_page_via_service(pool, notebook_id, persona_id, "Starlette", "ASGI framework")
        await insert_history_event(pool, history_id, "Learned that FastAPI is built on Starlette")

        mock_actions = {
            "create_notes": [], "update_notes": [], "merge_notes": [],
            "delete_notes": [], "update_categories": [],
            "extract_relations": [
                {
                    "source_title": "FastAPI",
                    "relation_type": "built_on",
                    "target_title": "Starlette",
                    "confidence": 0.95,
                }
            ],
            "health": {},
        }

        with patch.object(sleep_service, "_llm_curate", new=AsyncMock(return_value=mock_actions)):
            with patch.object(sleep_service, "_generate_monologue_text", new=AsyncMock(return_value="Learnt about FastAPI.")):
                await sleep_service.curate(persona_id)

        rel = await pool.fetchrow(
            """
            SELECT pr.relation_type, pr.confidence
            FROM page_relations pr
            JOIN notebook_pages src ON src.id = pr.source_page_id
            JOIN notebook_pages tgt ON tgt.id = pr.target_page_id
            WHERE src.name = 'FastAPI' AND tgt.name = 'Starlette'
              AND pr.valid_until IS NULL
            """
        )
        relation_created = rel is not None and rel["relation_type"] == "built_on"
        return EvalResult(
            suite=self.name, scenario_id=sid, description=description,
            metrics={"relation_created": float(relation_created)},
            passed=relation_created,
        )

    async def _scenario_delete_notes(
        self, pool: asyncpg.Pool, sid: str, description: str
    ) -> EvalResult:
        from backend.services import sleep_service  # noqa: PLC0415

        persona = await make_persona(pool)
        persona_id, history_id, notebook_id = (
            persona["id"], persona["history_id"], persona["notebook_id"]
        )

        page_id = await insert_page_via_service(
            pool, notebook_id, persona_id,
            name="Old deprecated notes",
            content="This content is outdated.",
        )
        await insert_history_event(pool, history_id, "Decided to remove old deprecated notes")

        mock_actions = {
            "create_notes": [], "update_notes": [], "merge_notes": [],
            "delete_notes": [str(page_id)],
            "update_categories": [], "extract_relations": [], "health": {},
        }

        with patch.object(sleep_service, "_llm_curate", new=AsyncMock(return_value=mock_actions)):
            with patch.object(sleep_service, "_generate_monologue_text", new=AsyncMock(return_value="Deleted old notes.")):
                await sleep_service.curate(persona_id)

        still_exists = await pool.fetchval(
            "SELECT id FROM notebook_pages WHERE id = $1", page_id
        )
        deleted = still_exists is None
        return EvalResult(
            suite=self.name, scenario_id=sid, description=description,
            metrics={"page_deleted": float(deleted)},
            passed=deleted,
        )

    async def _scenario_watermark(
        self, pool: asyncpg.Pool, sid: str, description: str
    ) -> EvalResult:
        from backend.services import sleep_service  # noqa: PLC0415

        persona = await make_persona(pool)
        persona_id, history_id, _ = (
            persona["id"], persona["history_id"], persona["notebook_id"]
        )

        await insert_history_event(pool, history_id, "Event one")
        await insert_history_event(pool, history_id, "Event two")

        mock_actions = {
            "create_notes": [], "update_notes": [], "merge_notes": [],
            "delete_notes": [], "update_categories": [],
            "extract_relations": [], "health": {},
        }

        with patch.object(sleep_service, "_llm_curate", new=AsyncMock(return_value=mock_actions)):
            with patch.object(sleep_service, "_generate_monologue_text", new=AsyncMock(return_value="Session.")):
                await sleep_service.curate(persona_id)

        watermark = await pool.fetchrow(
            "SELECT last_event_at FROM sleep_watermarks WHERE persona_id = $1", persona_id
        )
        advanced = watermark is not None and watermark["last_event_at"] is not None
        return EvalResult(
            suite=self.name, scenario_id=sid, description=description,
            metrics={"watermark_advanced": float(advanced)},
            passed=advanced,
        )

    # ------------------------------------------------------------------
    # LLM quality scenarios (expensive, off by default)
    # ------------------------------------------------------------------

    async def _run_llm_quality_scenarios(self, pool: asyncpg.Pool) -> list[EvalResult]:
        from evals.judges.llm_judge import judge_curation_quality  # noqa: PLC0415

        results = []

        async def _quality_scenario(
            events: list[str],
            expected_topic: str,
        ) -> EvalResult:
            from backend.services import sleep_service  # noqa: PLC0415

            persona = await make_persona(pool)
            persona_id, history_id, notebook_id = (
                persona["id"], persona["history_id"], persona["notebook_id"]
            )
            for ev in events:
                await insert_history_event(pool, history_id, ev)

            result = await sleep_service.curate(persona_id)
            await truncate_all(pool)

            if result.get("status") != "ok":
                return EvalResult(
                    suite=self.name, scenario_id="sa_llm_quality",
                    description=f"LLM curation quality: {expected_topic}",
                    metrics={}, passed=False,
                    error=f"Curation returned status: {result.get('status')}",
                )

            created = result.get("actions", {}).get("create_notes", [])
            if not created:
                return EvalResult(
                    suite=self.name, scenario_id="sa_llm_quality",
                    description=f"LLM curation quality: {expected_topic}",
                    metrics={"note_created": 0.0}, passed=False,
                    error="No notes created",
                )

            note = created[0]
            judge = await judge_curation_quality(events, note["name"], note.get("content", ""))

            passed = judge.score >= cfg.curation_min_quality
            return EvalResult(
                suite=self.name, scenario_id="sa_llm_quality",
                description=f"LLM curation quality: {expected_topic}",
                metrics={"quality": judge.score},
                passed=passed,
                details={"verdict": judge.verdict, "reasoning": judge.reasoning},
            )

        results.append(await _quality_scenario(
            events=[
                "Implemented Redis caching for session tokens",
                "Set TTL to 15 minutes",
                "Deployed to staging; cache hit rate is 87%",
            ],
            expected_topic="Redis caching",
        ))

        return results

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, float]:
        return {
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else 0.0,
        }

    @staticmethod
    def passes(aggregate: dict[str, float]) -> bool:
        return aggregate.get("pass_rate", 0) >= 0.80


# Helpers
async def insert_page_via_service(
    pool: asyncpg.Pool,
    notebook_id,
    persona_id,
    name: str,
    content: str,
    keywords: list[str] | None = None,
) -> uuid.UUID:
    from evals.harness import insert_page  # noqa: PLC0415
    return await insert_page(
        pool, notebook_id=notebook_id, name=name, content=content,
        keywords=keywords or [], persona_id=persona_id,
    )
