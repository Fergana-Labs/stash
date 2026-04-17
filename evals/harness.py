"""Core evaluation harness — orchestrates suites, collects results, drives reports."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg


@dataclass
class EvalResult:
    """Result for a single scenario."""

    suite: str
    scenario_id: str
    description: str
    metrics: dict[str, float]
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def summary_line(self) -> str:
        status = "✓" if self.passed else "✗"
        metrics_str = "  ".join(
            f"{k}={v:.3f}" for k, v in self.metrics.items()
        )
        return f"  {status} [{self.scenario_id}] {self.description}  {metrics_str}"


@dataclass
class SuiteResult:
    """Aggregated result for a full eval suite."""

    suite: str
    results: list[EvalResult]
    aggregate: dict[str, float]
    duration_s: float
    passed: bool

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def failed(self) -> list[EvalResult]:
        return [r for r in self.results if not r.passed]


def _average(results: list[EvalResult], key: str) -> float:
    vals = [r.metrics[key] for r in results if key in r.metrics]
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# Fixture helpers shared across suites
# ---------------------------------------------------------------------------

async def make_persona(pool: asyncpg.Pool, name: str | None = None) -> dict:
    """Insert a minimal persona with a linked history and notebook."""
    name = name or f"eval_persona_{uuid.uuid4().hex[:8]}"
    api_key = f"mc_{uuid.uuid4().hex}"
    import hashlib
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    user = await pool.fetchrow(
        "INSERT INTO users (name, type, api_key_hash) VALUES ($1, 'persona', $2) RETURNING id",
        name, api_key_hash,
    )
    persona_id = user["id"]

    history = await pool.fetchrow(
        "INSERT INTO histories (name, created_by) VALUES ($1, $2) RETURNING id",
        f"{name}_history", persona_id,
    )
    notebook = await pool.fetchrow(
        "INSERT INTO notebooks (name, created_by) VALUES ($1, $2) RETURNING id",
        f"{name}_notebook", persona_id,
    )
    await pool.execute(
        "UPDATE users SET history_id = $1, notebook_id = $2 WHERE id = $3",
        history["id"], notebook["id"], persona_id,
    )
    return {
        "id": persona_id,
        "api_key": api_key,
        "history_id": history["id"],
        "notebook_id": notebook["id"],
    }


async def insert_page(
    pool: asyncpg.Pool,
    notebook_id: uuid.UUID,
    name: str,
    content: str,
    keywords: list[str] | None = None,
    auto_inject: bool = False,
    importance: float = 0.5,
    persona_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a notebook page and return its ID."""
    import json as _json

    meta: dict[str, Any] = {
        "keywords": keywords or [],
        "importance": importance,
    }
    if auto_inject:
        meta["auto_inject"] = "always"

    row = await pool.fetchrow(
        """
        INSERT INTO notebook_pages
            (notebook_id, name, content_markdown, metadata, created_by, updated_by)
        VALUES ($1, $2, $3, $4, $5, $5)
        RETURNING id
        """,
        notebook_id,
        name,
        content,
        meta,
        persona_id,
    )
    return row["id"]


async def insert_history_event(
    pool: asyncpg.Pool,
    history_id: uuid.UUID,
    content: str,
    agent_name: str = "eval_agent",
    event_type: str = "tool_use",
) -> uuid.UUID:
    """Insert a history event and return its ID."""
    row = await pool.fetchrow(
        """
        INSERT INTO history_events (store_id, agent_name, event_type, content)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        history_id, agent_name, event_type, content,
    )
    return row["id"]


# ---------------------------------------------------------------------------
# Bulk data helpers for degradation / stress testing
# ---------------------------------------------------------------------------

_DISTRACTOR_TOPICS = [
    "machine learning", "database migration", "frontend styling", "deployment",
    "monitoring", "caching", "authentication", "webhooks", "file uploads",
    "search indexing", "notifications", "rate limiting", "logging", "testing",
    "documentation", "CI/CD", "docker", "kubernetes", "terraform", "graphql",
]


async def bulk_insert_pages(
    pool: asyncpg.Pool,
    notebook_id: uuid.UUID,
    persona_id: uuid.UUID,
    n: int,
    topic_prefix: str = "Distractor",
) -> list[uuid.UUID]:
    """Insert *n* noise pages to simulate a bloated notebook.

    Each page has plausible content and keywords drawn from a rotating pool
    of tech topics so FTS considers them as candidates without being truly
    relevant to the test query.
    """
    import random

    ids: list[uuid.UUID] = []
    for i in range(n):
        topic = _DISTRACTOR_TOPICS[i % len(_DISTRACTOR_TOPICS)]
        extra = random.choice(_DISTRACTOR_TOPICS)
        content = (
            f"Notes on {topic} (entry {i}). "
            f"This page covers aspects of {topic} including best practices, "
            f"common pitfalls, and integration with {extra}. "
            f"Reference material for the team."
        )
        keywords = [topic.split()[0], extra.split()[0], f"ref_{i}"]
        pid = await insert_page(
            pool,
            notebook_id=notebook_id,
            name=f"{topic_prefix} — {topic} #{i}",
            content=content,
            keywords=keywords,
            persona_id=persona_id,
        )
        ids.append(pid)
    return ids


async def run_injection_loop(
    persona_id: uuid.UUID,
    notebook_id: uuid.UUID,
    history_id: uuid.UUID,
    prompt_text: str,
    rounds: int,
) -> list[dict]:
    """Call compute_injection *rounds* times, chaining session state.

    Returns the list of result dicts (one per round) so callers can inspect
    what was injected at each step.
    """
    from backend.services import injection_service

    session_state: dict = {
        "prompt_num": 0,
        "session_start": "2025-01-01T00:00:00",
        "items": {},
    }
    results: list[dict] = []
    for _ in range(rounds):
        result = await injection_service.compute_injection(
            agent_id=persona_id,
            notebook_id=notebook_id,
            history_id=history_id,
            prompt_text=prompt_text,
            session_state_data=session_state,
        )
        results.append(result)
        session_state = result["updated_session_state"]
    return results


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------

class EvalHarness:
    """Orchestrates loading suites, running scenarios, and collecting results."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._suite_registry: dict[str, Any] = {}

    def register(self, name: str, suite: Any) -> None:
        self._suite_registry[name] = suite

    async def run(self, suite_names: list[str] | None = None) -> list[SuiteResult]:
        names = suite_names or list(self._suite_registry)
        results: list[SuiteResult] = []
        for name in names:
            suite = self._suite_registry.get(name)
            if suite is None:
                raise ValueError(f"Unknown suite: {name!r}. Available: {list(self._suite_registry)}")
            t0 = time.monotonic()
            suite_results = await suite.run(self.pool)
            duration = time.monotonic() - t0
            agg = suite.aggregate(suite_results)
            passed = suite.passes(agg)
            results.append(
                SuiteResult(
                    suite=name,
                    results=suite_results,
                    aggregate=agg,
                    duration_s=duration,
                    passed=passed,
                )
            )
        return results
