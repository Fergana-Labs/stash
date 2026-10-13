"""Monitoring windows, prompt attribution and ownership with real Postgres."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.services.rm import monitoring, optimization

from .test_rm_api import _register
from .test_rm_datasets import _user_id
from .test_rm_precompute import ready

BASE = "/api/v1/rm/optimizations/monitoring"


async def enabled(client, pool):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await pool.execute(
        "UPDATE users SET reward_models_enabled=true,product_checkpoint='latest' WHERE id=$1", owner
    )
    return auth, owner


async def trace(pool, owner, model, n, credits, *, agent="codex", fresh=True):
    when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=n)
    tid = await pool.fetchval(
        """INSERT INTO rm_traces(owner_user_id,external_id,title,source_format,metadata,created_at)
        VALUES($1,$2,$2,'stash',$3,$4) RETURNING id""",
        owner,
        str(uuid4()),
        {"agent": agent},
        when,
    )
    for i, credit in enumerate(credits):
        step = await pool.fetchval(
            """INSERT INTO rm_trace_steps(trace_id,idx,role,content)
            VALUES($1,$2,'assistant','answer') RETURNING id""",
            tid,
            i,
        )
        await pool.execute(
            "INSERT INTO rm_action_scores(reward_model_id,step_id,score,credit) VALUES($1,$2,$3,$3)",
            model,
            step,
            credit,
        )
    await pool.execute(
        """INSERT INTO rm_scoring_runs(owner_user_id,trace_id,reward_model_id,status,trace_updated_at,model_finished_at)
        SELECT $1,t.id,m.id,'succeeded',t.updated_at,m.finished_at FROM rm_traces t
        CROSS JOIN rm_reward_models m WHERE t.id=$2 AND m.id=$3""",
        owner,
        tid,
        model,
    )
    if not fresh:
        await pool.execute(
            "UPDATE rm_traces SET updated_at=updated_at+interval '1 second' WHERE id=$1", tid
        )
    return tid


async def program(pool, owner, model, agent="codex"):
    pid = await pool.fetchval(
        """INSERT INTO rm_optimizations(owner_user_id,reward_model_id,name,agent,scope,metric,status,runs_per_arm,max_rounds)
        VALUES($1,$2,'Improve support',$3,'support/refunds',$4,'active',20,10) RETURNING id""",
        owner,
        model,
        agent,
        {
            "name": "Accepted",
            "unit": "0 or 1",
            "direction": "higher",
            "minimum": 0,
            "maximum": 1,
            "regression_tolerance": 0,
        },
    )
    revisions = []
    for v in (1, 2):
        revisions.append(
            await pool.fetchval(
                "INSERT INTO rm_prompt_revisions(optimization_id,version,content,rationale) VALUES($1,$2,$3,'Recorded rationale') RETURNING id",
                pid,
                v,
                f"Instructions v{v}",
            )
        )
    await pool.execute(
        "UPDATE rm_optimizations SET active_revision_id=$2 WHERE id=$1", pid, revisions[1]
    )
    return pid, revisions


async def test_agent_roster_includes_unconnected_and_optimization_only_agents_without_leaking(
    client, pool
):
    auth, owner = await enabled(client, pool)
    other_auth, other = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    other_model, _ = await ready(client, pool, other_auth)
    await trace(pool, owner, model, 0, [0.2])
    await trace(pool, other, other_model, 0, [0.9], agent="private-agent")
    pid, revisions = await program(pool, owner, model, "support")
    await program(pool, other, other_model, "private-agent")
    await pool.execute(
        "INSERT INTO rm_trace_sources(owner_user_id,source_id,name) VALUES($1,'codex','My coding agent')",
        owner,
    )
    response = await client.get(BASE, headers=auth)
    assert response.status_code == 200, response.text
    data = response.json()
    assert {a["agent"] for a in data["agents"]} == {"codex", "support"}
    assert data["agents"][0]["display_name"] == "My coding agent"
    assert data["agents"][1]["trace_count"] == 0
    assert [p["id"] for p in data["programs"]] == [str(pid)]
    assert data["programs"][0]["active_revision_id"] == str(revisions[1])
    assert len(data["models"]) == 1
    assert "training_pairs" not in data["models"][0]


async def test_windows_weight_runs_equally_exclude_stale_scores_and_other_agents_and_models(
    client, pool
):
    auth, owner = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    other, _ = await ready(client, pool, auth)
    for n in range(40):
        await trace(pool, owner, model, n, [0.0] * 3 if n < 20 else [0.6])
    await trace(pool, owner, model, 41, [-1.0], fresh=False)
    await trace(pool, owner, model, 42, [-1.0], agent="different")
    await trace(pool, owner, other, 43, [-1.0])
    response = await client.get(
        f"{BASE}/rewards",
        headers=auth,
        params={"agent": "codex", "model_id": str(model), "window": 20},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 40
    assert data["mean"] == pytest.approx(0.3)
    assert data["current_mean"] == pytest.approx(0.6)
    assert data["previous_mean"] == 0
    assert data["current_n"] == data["previous_n"] == 20
    assert data["points"][0]["window_count"] == 1
    assert data["points"][20]["rolling_mean"] == pytest.approx(0.03)
    assert data["points"][-1]["rolling_mean"] == pytest.approx(0.6)
    # A changed checkpoint invalidates old rewards, including successful jobs.
    await pool.execute(
        "UPDATE rm_reward_models SET finished_at=finished_at+interval '1 second' WHERE id=$1", model
    )
    assert (await monitoring.rewards(owner, "codex", model, 20))["total"] == 0


async def test_prompt_windows_keep_arms_separate_and_aggregate_entire_history(client, pool):
    auth, owner = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    pid, revisions = await program(pool, owner, model)
    now = datetime.now(UTC)
    for n in range(120):
        rev = revisions[n % 2]
        await pool.execute(
            """INSERT INTO rm_optimization_runs(optimization_id,revision_id,work_key,capture_external_id,
            agent_version,arm,status,reward,assigned_at) VALUES($1,$2,$3,$3,'codex-1',$4,'completed',$5,$6)""",
            pid,
            rev,
            str(n),
            "baseline" if n % 2 == 0 else "candidate",
            0.1 if n % 2 == 0 else 0.7,
            now + timedelta(minutes=n),
        )
    history = await monitoring.rewards(owner, "codex", model, 20, pid)
    assert history["total"] == 120
    assert history["current_mean"] == pytest.approx(0.7)
    assert history["previous_mean"] == pytest.approx(0.7)
    assert all(
        p["rolling_mean"]
        == pytest.approx(0.1 if str(p["revision_id"]) == str(revisions[0]) else 0.7)
        for p in history["points"]
    )
    detail = await optimization.detail(owner, pid)
    assert len(detail["runs"]) == 100
    assert all(r["assigned"] == r["completed"] == 60 for r in detail["revision_stats"])
    with pytest.raises(ValueError):
        await monitoring.rewards(owner, "wrong-agent", model, 20, pid)
    with pytest.raises(ValueError):
        await monitoring.rewards(owner, "codex", model, 21)
    other_auth, other = await enabled(client, pool)
    other_model, _ = await ready(client, pool, other_auth)
    denied = await client.get(
        f"{BASE}/rewards",
        headers=other_auth,
        params={"agent": "codex", "model_id": str(other_model), "program_id": str(pid)},
    )
    assert denied.status_code == 404
    denied = await client.get(
        f"{BASE}/rewards", headers=other_auth, params={"agent": "codex", "model_id": str(model)}
    )
    assert denied.status_code == 404


async def test_chart_thins_after_window_calculation_not_before(client, pool):
    auth, owner = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    pid, revisions = await program(pool, owner, model)
    await pool.execute(
        """INSERT INTO rm_optimization_runs(optimization_id,revision_id,work_key,capture_external_id,agent_version,arm,status,reward,assigned_at)
        SELECT $1,$2,n::text,n::text,'agent-1','current','completed',n/2000.0,
        '2026-01-01'::timestamptz+n*interval '1 minute' FROM generate_series(1,1001) n""",
        pid,
        revisions[1],
    )
    data = await monitoring.rewards(owner, "codex", model, 20, pid)
    assert data["total"] == 1001
    assert len(data["points"]) < 505
    assert data["points"][-1]["rolling_mean"] == pytest.approx(sum(range(982, 1002)) / 20 / 2000)
    assert data["points"][-1]["window_count"] == 20


async def test_monitoring_does_not_load_legacy_skill_trials_or_count_them_as_prompt_changes(
    client, pool
):
    auth, owner = await enabled(client, pool)
    other_auth, other = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    other_model, _ = await ready(client, pool, other_auth)
    for user, mid in [(owner, model), (other, other_model)]:
        await pool.execute(
            """INSERT INTO rm_gepa_runs(owner_user_id,reward_model_id,task_model,reflection_model,max_metric_calls,
            status,seed_score,best_score,candidates,best_skill) VALUES($1,$2,'agent-model','reflect-model',20,
            'succeeded',0.2,0.8,$3,'large skill body')""",
            user,
            mid,
            [{"skill": "candidate", "score": 0.8}],
        )
    data = await monitoring.overview(owner)
    assert data["gepa"] == []
    assert await pool.fetchval("SELECT count(*) FROM rm_gepa_runs") == 2
    assert data["programs"] == []


async def test_trace_rewards_use_saved_checkpoint_scores_and_waiting_program_history_stays_readable(
    client, pool
):
    auth, owner = await enabled(client, pool)
    model, _ = await ready(client, pool, auth)
    await pool.execute(
        "UPDATE rm_reward_models SET metrics=$2 WHERE id=$1", model, {"trace_scoring_version": 1}
    )
    tid = await trace(pool, owner, model, 0, [0.2])
    await pool.execute(
        "INSERT INTO rm_trace_scores(reward_model_id,trace_id,score) VALUES($1,$2,4.5)", model, tid
    )
    result = await monitoring.rewards(owner, "codex", model, 20)
    assert result["unit"] == "trace_reward"
    assert result["current_mean"] == 4.5
    await pool.execute("UPDATE rm_traces SET updated_at=now()+interval '1 second' WHERE id=$1", tid)
    assert (await monitoring.rewards(owner, "codex", model, 20))["total"] == 0
    pid, _ = await program(pool, owner, model)
    await pool.execute(
        "UPDATE rm_reward_models SET status='queued',metrics=NULL WHERE id=$1", model
    )
    await pool.execute("UPDATE rm_optimizations SET status='waiting_model' WHERE id=$1", pid)
    assert (await monitoring.rewards(owner, "codex", model, 20, pid))["total"] == 0
    response = await client.get(
        f"{BASE}/rewards",
        headers=auth,
        params={"agent": "codex", "model_id": str(model), "window": 21},
    )
    assert response.status_code == 422
