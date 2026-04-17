"""Evaluation system configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

EVALS_ROOT = Path(__file__).parent
DATASETS_DIR = EVALS_ROOT / "datasets"
REPORTS_DIR = EVALS_ROOT / "reports" / "output"


@dataclass
class EvalConfig:
    # Database
    test_db_url: str = field(
        default_factory=lambda: os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://octopus:octopus@localhost:5432/octopus_test",
        )
    )

    # LLM judge — uses Anthropic; set ANTHROPIC_API_KEY in env
    judge_model: str = field(
        default_factory=lambda: os.getenv("EVAL_JUDGE_MODEL", "claude-haiku-4-5")
    )
    # Timeout per LLM judge call (seconds)
    judge_timeout_s: float = 30.0

    # Retrieval thresholds (used as pass/fail gates in CI)
    retrieval_min_ndcg5: float = 0.60
    retrieval_min_mrr: float = 0.55
    retrieval_min_recall5: float = 0.60

    # KG thresholds
    kg_min_precision: float = 0.80
    kg_min_recall: float = 0.70

    # Sleep agent curation threshold (LLM judge score 0–1)
    curation_min_quality: float = 0.70

    # E2E task threshold (fraction of tasks with relevant context injected)
    e2e_min_hit_rate: float = 0.75

    # Degradation suite thresholds
    degradation_min_ndcg5: float = 0.40  # per-scale-level floor
    degradation_max_drop: float = 0.30   # max allowed NDCG drop from smallest → largest scale
    degradation_temporal_survival: float = 0.90  # always-inject page must appear ≥90% of rounds

    # Curation quality thresholds
    curation_min_retrieval_hit_rate: float = 0.60

    # Whether to run expensive LLM-judge suites (off by default for fast CI)
    run_llm_suites: bool = field(
        default_factory=lambda: os.getenv("EVAL_RUN_LLM_SUITES", "false").lower() == "true"
    )

    # Token budget for injection during evals
    injection_budget_tokens: int = 4000

    @classmethod
    def from_env(cls) -> "EvalConfig":
        return cls()


# Module-level singleton
cfg = EvalConfig.from_env()
