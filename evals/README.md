# Octopus Eval Suite

A quantitative evaluation framework for Octopus' core memory and retrieval
systems. Measures whether the platform actually helps agents perform better on
tasks.

---

## Architecture

```
evals/
  datasets/                            # JSONL scenario files (source of truth)
    retrieval_scenarios.jsonl           # 15 FTS retrieval scenarios
    kg_scenarios.jsonl                  # 8 knowledge graph scenarios
    task_scenarios.jsonl                # 8 end-to-end task scenarios
    degradation_scenarios.jsonl         # 9 scale/temporal/duplicate scenarios
    curation_quality_scenarios.jsonl    # 5 sleep-agent-through-retrieval scenarios

  suites/                 # One suite per subsystem
    retrieval.py          # P@k, R@k, NDCG@k, MRR
    kg_relations.py       # Relation upsert, neighbour lookup, invalidation
    sleep_agent.py        # Action executor correctness + optional LLM quality
    end_to_end.py         # Full pipeline task hit-rate
    degradation.py        # Scale degradation, temporal suppression, near-duplicate
    curation_quality.py   # Sleep-agent-through-retrieval E2E quality

  judges/
    metrics.py            # NDCG, MRR, Precision, Recall (no LLM)
    llm_judge.py          # LLM-as-judge via Claude (optional)

  reports/
    console.py            # Rich pretty-printing
    json_report.py        # Timestamped JSON output + baseline comparison

  harness.py              # EvalHarness orchestrator + bulk/loop helpers
  db.py                   # DB bootstrap (Alembic + asyncpg pool)
  config.py               # Thresholds and settings
  conftest.py             # pytest integration
  __main__.py             # CLI entrypoint
```

---

## Running evals

**Prerequisites:** the test Postgres database must be reachable
(same as `backend/tests/`).

```bash
# All suites
python -m evals

# Specific suites
python -m evals --suite retrieval
python -m evals --suite retrieval kg_relations

# With LLM-as-judge (requires ANTHROPIC_API_KEY)
EVAL_RUN_LLM_SUITES=true python -m evals --suite sleep_agent

# Override database
python -m evals --db postgresql://user:pass@host:5432/octopus_test

# Compare against a baseline
python -m evals --compare evals/reports/output/eval_20250101T120000Z.json

# Write results to a specific file
python -m evals --out /tmp/eval_results.json

# List available suites
python -m evals --list
```

**Via pytest:**

```bash
pytest evals/ -v
pytest evals/ -v -k retrieval
EVAL_RUN_LLM_SUITES=true pytest evals/ -v -k sleep_agent
```

---

## Suites

### `retrieval`
Tests whether `injection_service.compute_injection()` surfaces the right
notebook pages for a given query.

| Metric | Threshold | Notes |
|--------|-----------|-------|
| NDCG@5 | ≥ 0.60 | Graded relevance |
| MRR    | ≥ 0.55 | First-hit rank |
| R@5    | ≥ 0.60 | Coverage of relevant pages |

Scenarios cover: exact match, semantic similarity, buried keywords, no results,
multi-page answers, always-inject, synonym matching, code retrieval.

### `kg_relations`
Tests the knowledge graph layer: `upsert_relation`, `get_page_neighbors`,
confidence filtering, and temporal invalidation.

| Metric | Threshold |
|--------|-----------|
| Precision | ≥ 0.80 |
| Recall    | ≥ 0.70 |

Scenarios cover: `built_with`, `depends_on`, `part_of`, `supersedes`,
multi-relation, bidirectional lookup, confidence threshold, invalidation.

### `sleep_agent`
Tests the action executor (always runs, no LLM needed):
- `create_notes` → page created
- `update_notes` → content appended
- `extract_relations` → relation upserted
- `delete_notes` → page removed
- Watermark advances after events

LLM quality mode (`EVAL_RUN_LLM_SUITES=true`): runs real curation and uses
Claude as a judge (accuracy, completeness, no hallucination).

### `end_to_end`
Measures the fraction of tasks where the right context is injected.

| Metric | Threshold |
|--------|-----------|
| avg_hit_rate | ≥ 0.75 |

Scenarios cover: factual lookup, procedure, multi-source, ADR retrieval,
status check, no-relevant-context, graph-expanded, always-inject.

### `degradation`
Stress-tests the memory pipeline under three failure modes:

**Scale degradation** — runs the same retrieval query at 10, 100, 500, and
1000 notebook pages. Asserts NDCG@5 doesn't drop more than 30% from the
smallest to the largest scale level.

**Temporal suppression** — runs `compute_injection` in a multi-round loop
(up to 25 rounds), chaining session state. Tests that:
- `auto_inject: always` pages appear ≥90% of rounds
- High-relevance pages eventually reappear after spaced repetition windows
- Irrelevant pages correctly fade from results over time

**Near-duplicate disambiguation** — inserts multiple versions of the same
page (e.g., "Rate limiting v1" through "Rate limiting v5 (current)") and
verifies the current version ranks in the top 2. Also tests contradiction
resolution (e.g., outdated vs. updated location info).

| Metric | Threshold |
|--------|-----------|
| degradation_pct | ≤ 0.30 (max NDCG drop across scale levels) |
| temporal_survival | ≥ 0.90 (always-inject page appearance rate) |
| current_rank | ≤ 2 (newest version must rank top-2) |
| overall pass_rate | ≥ 0.60 |

### `curation_quality`
End-to-end sleep-agent-through-retrieval test. Tests the full pipeline:

1. Feeds history events to the sleep agent
2. Sleep agent curates the notebook (mocked by default, real LLM with `--llm`)
3. Runs retrieval queries against the notebook the agent created
4. Measures whether the curated pages are actually retrievable

| Metric | Threshold |
|--------|-----------|
| retrieval_hit_rate | ≥ 0.60 (fraction of queries where expected keywords appear in context) |

With `EVAL_RUN_LLM_SUITES=true`: also runs LLM-as-judge on structural
quality (keyword coverage, page deduplication, topic completeness).

---

## Adding scenarios

Scenarios are plain JSONL files — one JSON object per line. Add lines to the
relevant file in `evals/datasets/`:

```jsonl
{"id": "ret_016", "description": "...", "pages": [...], "query": "...", "relevant": [{"name": "...", "grade": 3}]}
```

Grades: `3` = highly relevant, `2` = relevant, `1` = marginal, `0` = not relevant.
`grade >= 2` counts as "relevant" for binary metrics (P@k, R@k).

---

## CI integration

**Every push/PR** — `.github/workflows/test.yml` runs all six suites
(retrieval, kg_relations, sleep_agent, end_to_end, degradation,
curation_quality) after `backend-test`. Results uploaded as artifacts.

**Nightly** — `.github/workflows/eval-nightly.yml` runs degradation +
curation_quality with full scale levels (1000-page inserts) and compares
against a checked-in `evals/reports/output/baseline.json` if present.
Runs at 2 AM UTC daily. Can also be triggered manually.

To add a regression gate: set thresholds in `evals/config.py` and the
eval jobs will fail if any aggregate metric drops below them.

To compare PRs against main:
1. Download the `eval-results-<main-sha>` artifact
2. Run `python -m evals --compare eval_<main-sha>.json`

---

## Configuration

Set via environment variables or edit `evals/config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_DATABASE_URL` | `postgresql://octopus:octopus@localhost:5432/octopus_test` | Test DB |
| `EVAL_RUN_LLM_SUITES` | `false` | Enable LLM-as-judge |
| `EVAL_JUDGE_MODEL` | `claude-haiku-4-5` | Anthropic model for judging |
| `ANTHROPIC_API_KEY` | — | Required for LLM suites |
