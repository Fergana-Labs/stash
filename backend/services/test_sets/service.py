"""Test sets, their cases, and runs compared with a baseline."""

from __future__ import annotations

import logging
from uuid import UUID

from ...database import get_pool
from . import scoring

log = logging.getLogger(__name__)

MAX_CASES = 2_000
EXPECTED_CHARS = 20_000


class NotFound(LookupError):
    pass


def _set(row) -> dict:
    return dict(row)


async def _owned(owner_id: UUID, set_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM test_sets WHERE id = $1 AND owner_user_id = $2", set_id, owner_id
    )
    if row is None:
        raise NotFound("Test set not found")
    return dict(row)


async def _check_scorers(owner_id: UUID, scorers: list[dict]) -> list[dict]:
    """Validated scorers: 'expected', or an owned eval with at least one passing label."""
    out = []
    for s in scorers:
        if s.get("type") == "expected":
            out.append({"type": "expected"})
            continue
        if s.get("type") != "eval":
            raise ValueError(
                "A scorer is {'type': 'expected'} or {'type': 'eval', 'eval_id', 'pass_labels'}"
            )
        owned = await get_pool().fetchval(
            "SELECT 1 FROM intuition_models WHERE id = $1 AND owner_user_id = $2",
            UUID(str(s.get("eval_id"))),
            owner_id,
        )
        if not owned:
            raise NotFound("Eval not found")
        labels = [str(x) for x in s.get("pass_labels") or []]
        if not labels:
            raise ValueError("An eval scorer needs the labels that count as a pass")
        out.append({"type": "eval", "eval_id": str(s["eval_id"]), "pass_labels": labels})
    if not out:
        raise ValueError("A test set needs at least one scorer")
    return out


async def list_sets(owner_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT s.*, (SELECT count(*) FROM test_cases c WHERE c.set_id = s.id)::int AS case_count,
                  (SELECT row_to_json(r) FROM (SELECT id, label, status, summary, created_at FROM test_runs
                     WHERE set_id = s.id ORDER BY created_at DESC LIMIT 1) r) AS last_run
           FROM test_sets s WHERE s.owner_user_id = $1 ORDER BY s.updated_at DESC""",
        owner_id,
    )
    return [_set(r) for r in rows]


async def create_set(
    owner_id: UUID, name: str, description: str, scorers: list[dict] | None, max_regressions: int
) -> dict:
    scorers = await _check_scorers(owner_id, scorers or [{"type": "expected"}])
    try:
        row = await get_pool().fetchrow(
            """INSERT INTO test_sets (owner_user_id, name, description, scorers, max_regressions)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            owner_id, name, description, scorers, max_regressions,
        )  # fmt: skip
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise ValueError("A test set with that name already exists") from exc
        raise
    return _set(row)


async def resolve(owner_id: UUID, ref: str) -> dict:
    """A set by id or by name, for the CLI."""
    try:
        return await _owned(owner_id, UUID(ref))
    except (ValueError, NotFound):
        row = await get_pool().fetchrow(
            "SELECT * FROM test_sets WHERE owner_user_id = $1 AND name = $2", owner_id, ref
        )
        if row is None:
            raise NotFound(f"No test set named {ref!r}") from None
        return _set(row)


async def get_set(owner_id: UUID, set_id: UUID) -> dict:
    s = await _owned(owner_id, set_id)
    pool = get_pool()
    cases = await pool.fetch(
        "SELECT * FROM test_cases WHERE set_id = $1 ORDER BY created_at, id", set_id
    )
    runs = await pool.fetch(
        "SELECT id, label, status, error, baseline_run_id, summary, created_at, finished_at FROM test_runs WHERE set_id = $1 ORDER BY created_at DESC LIMIT 50",
        set_id,
    )
    return {**s, "cases": [dict(c) for c in cases], "runs": [dict(r) for r in runs]}


async def update_set(owner_id: UUID, set_id: UUID, changes: dict) -> dict:
    await _owned(owner_id, set_id)
    if "scorers" in changes:
        changes["scorers"] = await _check_scorers(owner_id, changes["scorers"])
    if changes.get("baseline_run_id"):
        ok = await get_pool().fetchval(
            "SELECT 1 FROM test_runs WHERE id = $1 AND set_id = $2 AND status = 'done'",
            changes["baseline_run_id"],
            set_id,
        )
        if not ok:
            raise ValueError("The baseline must be a finished run of this set")
    allowed = {
        k: v
        for k, v in changes.items()
        if k in ("name", "description", "scorers", "max_regressions", "baseline_run_id")
    }
    if allowed:
        cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(allowed))
        await get_pool().execute(
            f"UPDATE test_sets SET {cols}, updated_at = now() WHERE id = $1",
            set_id,
            *allowed.values(),
        )
    return await get_set(owner_id, set_id)


async def delete_set(owner_id: UUID, set_id: UUID) -> None:
    await _owned(owner_id, set_id)
    await get_pool().execute("DELETE FROM test_sets WHERE id = $1", set_id)


async def add_cases(owner_id: UUID, set_id: UUID, cases: list[dict]) -> list[dict]:
    await _owned(owner_id, set_id)
    pool = get_pool()
    have = await pool.fetchval("SELECT count(*) FROM test_cases WHERE set_id = $1", set_id)
    if have + len(cases) > MAX_CASES:
        raise ValueError(f"A test set holds at most {MAX_CASES} cases")
    rows = []
    async with pool.acquire() as conn, conn.transaction():
        for c in cases:
            if not scoring.messages(c.get("input")) or not scoring.as_text(c["input"]).strip():
                raise ValueError("Every case needs an input")
            rows.append(
                await conn.fetchrow(
                    """INSERT INTO test_cases (set_id, name, input, expected, source_trace_id)
                       VALUES ($1, $2, $3, $4, $5) RETURNING *""",
                    set_id,
                    (c.get("name") or "")[:200],
                    c["input"],
                    (c.get("expected") or None) and str(c["expected"])[:EXPECTED_CHARS],
                    c.get("source_trace_id"),
                )  # fmt: skip
            )
        await conn.execute("UPDATE test_sets SET updated_at = now() WHERE id = $1", set_id)
    return [dict(r) for r in rows]


async def case_from_trace(
    owner_id: UUID, set_id: UUID, trace_id: UUID, upto_idx: int | None, expected: str | None
) -> dict:
    """A case from a production trace: the conversation up to a user turn as the input,
    and the expected answer given, or else the answer the agent gave there."""
    pool = get_pool()
    trace = await pool.fetchrow(
        "SELECT title FROM rm_traces WHERE id = $1 AND owner_user_id = $2", trace_id, owner_id
    )
    if trace is None:
        raise NotFound("Trace not found")
    steps = await pool.fetch(
        "SELECT idx, role, content, tool_name FROM rm_trace_steps WHERE trace_id = $1 ORDER BY idx",
        trace_id,
    )
    turns = [
        s
        for s in steps
        if s["role"] in ("user", "assistant")
        and not s["tool_name"]
        and (s["content"] or "").strip()
    ]
    users = [
        i
        for i, s in enumerate(turns)
        if s["role"] == "user" and (upto_idx is None or s["idx"] <= upto_idx)
    ]
    if not users:
        raise ValueError("The trace has no user message to start from")
    cut = users[-1] if upto_idx is not None else users[0]
    history = [{"role": s["role"], "content": s["content"]} for s in turns[: cut + 1]]
    if expected is None:
        answer = next((s["content"] for s in turns[cut + 1 :] if s["role"] == "assistant"), None)
        expected = answer
    case_input = history[0]["content"] if len(history) == 1 else history
    [created] = await add_cases(
        owner_id,
        set_id,
        [
            {
                "name": trace["title"] or "",
                "input": case_input,
                "expected": expected,
                "source_trace_id": trace_id,
            }
        ],
    )
    return created


async def update_case(owner_id: UUID, set_id: UUID, case_id: UUID, changes: dict) -> dict:
    await _owned(owner_id, set_id)
    sets = {k: v for k, v in changes.items() if k in ("name", "input", "expected")}
    if not sets:
        raise ValueError("Nothing to change")
    cols = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(sets))
    row = await get_pool().fetchrow(
        f"UPDATE test_cases SET {cols} WHERE id = $1 AND set_id = $2 RETURNING *",
        case_id,
        set_id,
        *sets.values(),
    )
    if row is None:
        raise NotFound("Case not found")
    return dict(row)


async def delete_case(owner_id: UUID, set_id: UUID, case_id: UUID) -> None:
    await _owned(owner_id, set_id)
    await get_pool().execute(
        "DELETE FROM test_cases WHERE id = $1 AND set_id = $2", case_id, set_id
    )


# ── Runs ─────────────────────────────────────────────────────────────────


async def start_run(
    owner_id: UUID, set_id: UUID, label: str, outputs: list[dict], baseline_run_id: UUID | None
) -> dict:
    """Record a version's outputs; scoring happens in the background."""
    s = await _owned(owner_id, set_id)
    pool = get_pool()
    cases = {
        str(r["id"]): r
        for r in await pool.fetch("SELECT id, name FROM test_cases WHERE set_id = $1", set_id)
    }
    by_name = {r["name"]: cid for cid, r in cases.items() if r["name"]}
    rows = []
    for o in outputs:
        cid = str(o.get("case_id") or by_name.get(o.get("case_name") or "") or "")
        if cid not in cases:
            raise ValueError(f"Unknown case {o.get('case_id') or o.get('case_name')!r}")
        rows.append((UUID(cid), str(o.get("output") or ""), o.get("trace_id")))
    if not rows:
        raise ValueError("A run needs at least one output")
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError("Each case can have one output per run")
    baseline = (
        baseline_run_id
        or s["baseline_run_id"]
        or await pool.fetchval(
            "SELECT id FROM test_runs WHERE set_id = $1 AND status = 'done' ORDER BY created_at DESC LIMIT 1",
            set_id,
        )
    )
    async with pool.acquire() as conn, conn.transaction():
        run = await conn.fetchrow(
            "INSERT INTO test_runs (set_id, owner_user_id, label, baseline_run_id) VALUES ($1, $2, $3, $4) RETURNING *",
            set_id, owner_id, label[:120], baseline,
        )  # fmt: skip
        await conn.executemany(
            "INSERT INTO test_results (run_id, case_id, output, trace_id) VALUES ($1, $2, $3, $4)",
            [(run["id"], cid, out, UUID(str(tid)) if tid else None) for cid, out, tid in rows],
        )
    from ...tasks import test_sets as tasks

    tasks.score_run.delay(str(run["id"]))
    return dict(run)


def compare(results: list[dict], baseline: dict[str, bool] | None, max_regressions: int) -> dict:
    """Pass rates, and against the baseline which cases broke and which got fixed."""
    n = len(results)
    passed = sum(bool(r["passed"]) for r in results)
    per_scorer: dict[str, list[bool]] = {}
    for r in results:
        for sc in r["scores"]:
            key = "expected" if sc["scorer"] == "expected" else f"eval:{sc['eval_id']}"
            per_scorer.setdefault(key, []).append(bool(sc["passed"]))
    out = {
        "cases": n,
        "passed": passed,
        "pass_rate": passed / n if n else None,
        "errors": sum(1 for r in results if r.get("error")),
        "scorers": {k: sum(v) / len(v) for k, v in per_scorer.items()},
    }
    if baseline is None:
        return {**out, "baseline": None, "broke": [], "fixed": [], "gate": "pass"}
    broke = [
        str(r["case_id"])
        for r in results
        if baseline.get(str(r["case_id"])) is True and not r["passed"]
    ]
    fixed = [
        str(r["case_id"])
        for r in results
        if baseline.get(str(r["case_id"])) is False and r["passed"]
    ]
    shared = [r for r in results if str(r["case_id"]) in baseline]
    base_rate = sum(baseline[str(r["case_id"])] for r in shared) / len(shared) if shared else None
    return {
        **out,
        "baseline": {"pass_rate": base_rate, "cases": len(shared)},
        "broke": broke,
        "fixed": fixed,
        "gate": "fail" if len(broke) > max_regressions else "pass",
    }


async def score_run(run_id: UUID) -> None:
    pool = get_pool()
    run = await pool.fetchrow(
        "SELECT r.*, s.scorers, s.max_regressions FROM test_runs r JOIN test_sets s ON s.id = r.set_id WHERE r.id = $1 AND r.status = 'scoring'",
        run_id,
    )
    if run is None:
        return
    try:
        rows = await pool.fetch(
            """SELECT res.id, res.case_id, res.output, res.trace_id, c.name, c.input, c.expected
               FROM test_results res JOIN test_cases c ON c.id = res.case_id WHERE res.run_id = $1""",
            run_id,
        )
        results = []
        for r in rows:
            case = {"name": r["name"], "input": r["input"], "expected": r["expected"]}
            try:
                scores, passed = await scoring.score(
                    run["owner_user_id"], run["scorers"], case, r["output"], r["trace_id"]
                )
                error = None
            except Exception as exc:  # One case failing to score must not sink the run.
                log.warning("Test case scoring failed: %s", type(exc).__name__)
                scores, passed, error = [], False, f"Scoring failed: {type(exc).__name__}"
            await pool.execute(
                "UPDATE test_results SET scores = $2, passed = $3, error = $4 WHERE id = $1",
                r["id"],
                scores,
                passed,
                error,
            )
            results.append(
                {"case_id": r["case_id"], "scores": scores, "passed": passed, "error": error}
            )
        baseline = None
        if run["baseline_run_id"]:
            baseline = {
                str(b["case_id"]): bool(b["passed"])
                for b in await pool.fetch(
                    "SELECT case_id, passed FROM test_results WHERE run_id = $1",
                    run["baseline_run_id"],
                )
            }
        summary = compare(results, baseline, run["max_regressions"])
        await pool.execute(
            "UPDATE test_runs SET status = 'done', summary = $2, finished_at = now() WHERE id = $1",
            run_id,
            summary,
        )
    except Exception as exc:
        log.exception("Test run %s failed", run_id)
        await pool.execute(
            "UPDATE test_runs SET status = 'failed', error = $2, finished_at = now() WHERE id = $1",
            run_id,
            f"Scoring failed: {type(exc).__name__}",
        )


async def get_run(owner_id: UUID, run_id: UUID) -> dict:
    pool = get_pool()
    run = await pool.fetchrow(
        "SELECT * FROM test_runs WHERE id = $1 AND owner_user_id = $2", run_id, owner_id
    )
    if run is None:
        raise NotFound("Run not found")
    results = await pool.fetch(
        """SELECT res.*, c.name AS case_name, c.input, c.expected,
                  b.passed AS baseline_passed, b.output AS baseline_output
           FROM test_results res JOIN test_cases c ON c.id = res.case_id
           LEFT JOIN test_results b ON b.run_id = $2 AND b.case_id = res.case_id
           WHERE res.run_id = $1 ORDER BY c.created_at, c.id""",
        run_id,
        run["baseline_run_id"],
    )
    return {**dict(run), "results": [dict(r) for r in results]}
