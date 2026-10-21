"""Exercise migration SQL against default scoring's real legacy table contract."""

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest_asyncio


async def migrate(conn, direction):
    path = Path(__file__).parents[1] / "migrations/versions/0238_rm_feature_jobs.py"
    spec = importlib.util.spec_from_file_location("private_scoring_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    module.op = SimpleNamespace(execute=statements.append)
    getattr(module, direction)()
    for statement in statements:
        await conn.execute(statement)


async def legacy_enqueue(conn, owner, trace, model):
    # This is main's pre-PR conflict target, intentionally kept unchanged.
    return await conn.fetchval(
        """INSERT INTO rm_scoring_runs
        (owner_user_id,trace_id,reward_model_id,automatic,trace_updated_at,model_finished_at)
        VALUES($1,$2,$3,false,now(),now())
        ON CONFLICT(trace_id,reward_model_id) WHERE status IN ('queued','running')
        DO NOTHING RETURNING id""",
        owner,
        trace,
        model,
    )


async def default_snapshot(conn):
    columns = await conn.fetch(
        """SELECT column_name,data_type,is_nullable,column_default
        FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name='rm_scoring_runs'
        ORDER BY ordinal_position"""
    )
    indexes = await conn.fetch(
        """SELECT indexname,indexdef FROM pg_indexes
        WHERE schemaname=current_schema() AND tablename='rm_scoring_runs'
        ORDER BY indexname"""
    )
    rows = await conn.fetch("SELECT * FROM rm_scoring_runs ORDER BY id")
    return columns, indexes, rows


@asynccontextmanager
async def rolled_back(conn):
    transaction = conn.transaction()
    await transaction.start()
    try:
        yield
    finally:
        await transaction.rollback()


@pytest_asyncio.fixture
async def legacy_schema(pool):
    # DDL and seeded rows are rolled back; the suite's public schema stays intact.
    async with pool.acquire() as conn, rolled_back(conn):
        schema = "rm_compat_" + uuid4().hex
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET LOCAL search_path TO "{schema}",public')
        for table in (
            "users",
            "rm_traces",
            "rm_reward_models",
            "rm_customer_heads",
            "rm_customer_feature_pairs",
        ):
            await conn.execute(f"CREATE TABLE {table}(id uuid PRIMARY KEY)")
        # Clone the real default contract installed by the full migration graph.
        # Indexes are copied with their original names in this isolated schema.
        await conn.execute(
            "CREATE TABLE rm_scoring_runs "
            "(LIKE public.rm_scoring_runs INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
        )
        indexes = await conn.fetch(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename='rm_scoring_runs' ORDER BY indexname"
        )
        for row in indexes:
            await conn.execute(
                row["indexdef"].replace("ON public.rm_scoring_runs", "ON rm_scoring_runs")
            )
        columns = {r["column_name"] for r in (await default_snapshot(conn))[0]}
        assert "customer_head_id" not in columns and "customer_scores" not in columns
        owner, trace, other_trace, model, head, other_head = [uuid4() for _ in range(6)]
        for table, values in (
            ("users", [owner]),
            ("rm_traces", [trace, other_trace]),
            ("rm_reward_models", [model]),
            ("rm_customer_heads", [head, other_head]),
        ):
            await conn.executemany(f"INSERT INTO {table}(id) VALUES($1)", [(v,) for v in values])
        initial = await legacy_enqueue(conn, owner, trace, model)
        assert initial and await legacy_enqueue(conn, owner, trace, model) is None
        await conn.execute(
            "UPDATE rm_scoring_runs SET progress=$2 WHERE id=$1", initial, {"stage": "waiting"}
        )
        yield conn, (owner, trace, other_trace, model, head, other_head), initial


async def private_enqueue(conn, owner, trace, model, head):
    return await conn.fetchval(
        """INSERT INTO rm_customer_scoring_runs
        (owner_user_id,trace_id,reward_model_id,customer_head_id,trace_updated_at,model_finished_at)
        VALUES($1,$2,$3,$4,now(),now())
        ON CONFLICT(trace_id,reward_model_id,customer_head_id)
        WHERE status IN ('queued','running') DO NOTHING RETURNING id""",
        owner,
        trace,
        model,
        head,
    )


async def test_upgrade_preserves_old_writers_and_separates_private_active_jobs(legacy_schema):
    conn, (owner, trace, other_trace, model, head, other_head), initial = legacy_schema
    before = await default_snapshot(conn)
    await migrate(conn, "upgrade")
    assert await default_snapshot(conn) == before
    assert await legacy_enqueue(conn, owner, trace, model) is None
    assert await legacy_enqueue(conn, owner, other_trace, model)
    private = await private_enqueue(conn, owner, trace, model, head)
    assert private and await private_enqueue(conn, owner, trace, model, head) is None
    assert await private_enqueue(conn, owner, trace, model, other_head)
    assert await conn.fetchval("SELECT count(*) FROM rm_customer_scoring_runs") == 2
    assert (
        await conn.fetchval("SELECT status FROM rm_scoring_runs WHERE id=$1", initial) == "queued"
    )
    # Old worker claims continue to see only the two default jobs.
    assert len(await conn.fetch("SELECT id FROM rm_scoring_runs WHERE status='queued'")) == 2


async def test_downgrade_discards_only_private_results_and_preserves_default_contract(
    legacy_schema,
):
    conn, (owner, trace, other_trace, model, head, _), initial = legacy_schema
    before = await default_snapshot(conn)
    await migrate(conn, "upgrade")
    private = await private_enqueue(conn, owner, trace, model, head)
    await conn.execute(
        "UPDATE rm_customer_scoring_runs SET status='succeeded',customer_scores=$2 WHERE id=$1",
        private,
        {"actions": [{"score": 0.5}]},
    )
    await migrate(conn, "downgrade")
    assert await default_snapshot(conn) == before
    assert (
        await conn.fetchval("SELECT to_regclass(current_schema()||'.rm_customer_scoring_runs')")
        is None
    )
    assert (
        await conn.fetchval("SELECT to_regclass(current_schema()||'.rm_customer_feature_jobs')")
        is None
    )
    assert await legacy_enqueue(conn, owner, trace, model) is None
    assert await legacy_enqueue(conn, owner, other_trace, model)
    assert await conn.fetchval("SELECT progress FROM rm_scoring_runs WHERE id=$1", initial) == {
        "stage": "waiting"
    }
