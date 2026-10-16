"""Test sets: regression tests for agents.

A test set is a list of cases (an input and, optionally, the answer the agent
should give). A test run is one version of the agent's outputs for those
cases, scored by the set's scorers (evals, and a match against the expected
answer) and compared with a baseline run: which cases got fixed, which broke.

Revision ID: 0246
Revises: 0245
"""

from alembic import op

revision = "0246"
down_revision = "0245"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE test_sets (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
        description text NOT NULL DEFAULT '',
        scorers jsonb NOT NULL DEFAULT '[{"type": "expected"}]'::jsonb,
        max_regressions integer NOT NULL DEFAULT 0 CHECK (max_regressions >= 0),
        baseline_run_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (owner_user_id, name)
    )""")
    op.execute("""CREATE TABLE test_cases (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        set_id uuid NOT NULL REFERENCES test_sets(id) ON DELETE CASCADE,
        name text NOT NULL DEFAULT '',
        input jsonb NOT NULL,
        expected text,
        source_trace_id uuid REFERENCES rm_traces(id) ON DELETE SET NULL,
        -- clock_timestamp, not now(): cases added in one request keep their order.
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""")
    op.execute("CREATE INDEX test_cases_set ON test_cases (set_id, created_at)")
    op.execute("""CREATE TABLE test_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        set_id uuid NOT NULL REFERENCES test_sets(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        label text NOT NULL DEFAULT '',
        status text NOT NULL DEFAULT 'scoring' CHECK (status IN ('scoring', 'done', 'failed')),
        error text,
        baseline_run_id uuid REFERENCES test_runs(id) ON DELETE SET NULL,
        summary jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz
    )""")
    op.execute("CREATE INDEX test_runs_set ON test_runs (set_id, created_at DESC)")
    op.execute(
        "ALTER TABLE test_sets ADD CONSTRAINT test_sets_baseline FOREIGN KEY (baseline_run_id) "
        "REFERENCES test_runs(id) ON DELETE SET NULL"
    )
    op.execute("""CREATE TABLE test_results (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id uuid NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
        case_id uuid NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
        output text NOT NULL,
        trace_id uuid REFERENCES rm_traces(id) ON DELETE SET NULL,
        scores jsonb NOT NULL DEFAULT '[]'::jsonb,
        passed boolean,
        error text,
        UNIQUE (run_id, case_id)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE test_results")
    op.execute("ALTER TABLE test_sets DROP CONSTRAINT test_sets_baseline")
    op.execute("DROP TABLE test_runs")
    op.execute("DROP TABLE test_cases")
    op.execute("DROP TABLE test_sets")
