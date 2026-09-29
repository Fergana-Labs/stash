"""Reward model platform: traces, annotations, reward models, scores, GEPA runs.

Revision ID: 0208
Revises: 0207
"""

from alembic import op

revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_traces (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            external_id text,
            title text NOT NULL,
            source_format text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (owner_user_id, external_id)
        )
    """)
    op.execute("CREATE INDEX rm_traces_owner_created ON rm_traces (owner_user_id, created_at DESC)")

    # Raw OTLP/JSON spans from the live receiver. A trace's spans arrive across
    # several export batches, so each batch rebuilds the trace from all of them.
    op.execute("""
        CREATE TABLE rm_otel_spans (
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            otel_trace_id text NOT NULL,
            span_id text NOT NULL,
            span jsonb NOT NULL,
            received_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (owner_user_id, otel_trace_id, span_id)
        )
    """)

    op.execute("""
        CREATE TABLE rm_trace_steps (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
            idx integer NOT NULL,
            role text NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
            content text NOT NULL,
            tool_name text,
            tool_input jsonb,
            tool_call_id text,
            metadata jsonb,
            UNIQUE (trace_id, idx)
        )
    """)

    op.execute("""
        CREATE TABLE rm_annotations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
            step_id uuid REFERENCES rm_trace_steps(id) ON DELETE CASCADE,
            rating smallint CHECK (rating IN (-1, 1)),
            comment text,
            quote jsonb,
            label_error boolean NOT NULL DEFAULT false,
            label_error_note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT rm_annotations_rating_or_comment
                CHECK (rating IS NOT NULL OR comment IS NOT NULL),
            CONSTRAINT rm_annotations_quote_requires_step
                CHECK (quote IS NULL OR step_id IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX rm_annotations_trace ON rm_annotations (trace_id)")
    op.execute("CREATE INDEX rm_annotations_step ON rm_annotations (step_id)")
    op.execute("CREATE INDEX rm_annotations_owner ON rm_annotations (owner_user_id)")

    op.execute("""
        CREATE TABLE rm_reward_models (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            base_model text NOT NULL,
            compute text NOT NULL CHECK (compute IN ('local', 'modal')),
            epochs integer NOT NULL CHECK (epochs > 0),
            max_pairs integer NOT NULL CHECK (max_pairs > 0),
            -- The traces chosen for training. A trace deleted later just drops out.
            trace_ids uuid[] NOT NULL CHECK (cardinality(trace_ids) > 0),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            num_pairs integer,
            metrics jsonb,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz
        )
    """)
    op.execute(
        "CREATE INDEX rm_reward_models_owner_created "
        "ON rm_reward_models (owner_user_id, created_at DESC)"
    )

    op.execute("""
        CREATE TABLE rm_trace_scores (
            reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
            trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
            score double precision NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (reward_model_id, trace_id)
        )
    """)
    op.execute("CREATE INDEX rm_trace_scores_trace ON rm_trace_scores (trace_id)")

    op.execute("""
        CREATE TABLE rm_gepa_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
            skill_name text,
            skill_description text,
            task_model text NOT NULL,
            task_api_base text,
            reflection_model text NOT NULL,
            max_metric_calls integer NOT NULL CHECK (max_metric_calls > 0),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            seed_skill text,
            best_skill text,
            seed_score double precision,
            best_score double precision,
            candidates jsonb,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz
        )
    """)
    op.execute(
        "CREATE INDEX rm_gepa_runs_owner_created ON rm_gepa_runs (owner_user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE rm_gepa_runs")
    op.execute("DROP TABLE rm_trace_scores")
    op.execute("DROP TABLE rm_reward_models")
    op.execute("DROP TABLE rm_annotations")
    op.execute("DROP TABLE rm_trace_steps")
    op.execute("DROP TABLE rm_otel_spans")
    op.execute("DROP TABLE rm_traces")
