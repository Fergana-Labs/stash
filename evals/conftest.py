"""Pytest integration for the eval suites.

Allows running evals with pytest alongside the regular backend tests:

    pytest evals/ -v
    pytest evals/ -v -k retrieval
    EVAL_RUN_LLM_SUITES=true pytest evals/ -v -k sleep_agent

Fixtures are session-scoped so the DB is bootstrapped once per pytest run.
"""

from __future__ import annotations

import asyncio
import json
import os

import asyncpg
import pytest
import pytest_asyncio

_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://octopus:octopus@localhost:5432/octopus_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL


@pytest_asyncio.fixture(scope="session")
async def eval_pool():
    """Session-scoped asyncpg pool with Alembic migrations applied."""
    from evals.db import eval_db_pool

    async with eval_db_pool() as pool:
        yield pool


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(eval_pool):
    yield
    from evals.db import truncate_all
    await truncate_all(eval_pool)


# ------------------------------------------------------------------
# Suite-level tests (one test per suite, collected by pytest)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieval_suite(eval_pool):
    from evals.suites.retrieval import RetrievalSuite
    suite = RetrievalSuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"Retrieval suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"


@pytest.mark.asyncio
async def test_kg_relations_suite(eval_pool):
    from evals.suites.kg_relations import KGRelationsSuite
    suite = KGRelationsSuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"KG relations suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"


@pytest.mark.asyncio
async def test_sleep_agent_suite(eval_pool):
    from evals.suites.sleep_agent import SleepAgentSuite
    suite = SleepAgentSuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"Sleep agent suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"


@pytest.mark.asyncio
async def test_end_to_end_suite(eval_pool):
    from evals.suites.end_to_end import EndToEndSuite
    suite = EndToEndSuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"E2E suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"


@pytest.mark.asyncio
async def test_degradation_suite(eval_pool):
    from evals.suites.degradation import DegradationSuite
    suite = DegradationSuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"Degradation suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"


@pytest.mark.asyncio
async def test_curation_quality_suite(eval_pool):
    from evals.suites.curation_quality import CurationQualitySuite
    suite = CurationQualitySuite()
    results = await suite.run(eval_pool)
    agg = suite.aggregate(results)

    failed = [r for r in results if not r.passed]
    if failed:
        details = "\n".join(f"  {r.scenario_id}: {r.error or r.metrics}" for r in failed)
        pytest.fail(f"Curation quality suite: {len(failed)} scenarios failed:\n{details}")

    assert suite.passes(agg), f"Aggregate metrics below threshold: {agg}"
