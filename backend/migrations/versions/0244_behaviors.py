"""Behaviors: named patterns tagged on exact windows of traces, plus searchable segments.

A behavior is something a team wants to watch across production traces -- what the
user does (repeats a request after a miss), what the agent does (claims a fix it never
checked), or what the environment hands back (an empty search). Each detection is a
hit on a step window [start_idx, end_idx] with verbatim evidence, so it can be
reviewed, trended, searched and turned into eval examples.

Segments are the searchable unit of a trace: a user turn and the agent's work until
the next one. They are embedded by the embedding reconciler.

Revision ID: 0244
Revises: 0243
"""

from alembic import op

revision = "0244"
down_revision = "0243"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE behaviors (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
        slug text NOT NULL,
        actor text NOT NULL CHECK (actor IN ('user', 'agent', 'environment')),
        definition text NOT NULL DEFAULT '',
        examples jsonb NOT NULL DEFAULT '[]'::jsonb,
        detector text NOT NULL CHECK (detector IN ('rule', 'llm', 'agent_judge')),
        rule jsonb,
        severity text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high')),
        enabled boolean NOT NULL DEFAULT true,
        alert jsonb,
        last_alert_at timestamptz,
        eval_id uuid REFERENCES intuition_models(id) ON DELETE SET NULL,
        version integer NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (owner_user_id, slug)
    )""")

    op.execute("""CREATE TABLE behavior_hits (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        behavior_id uuid NOT NULL REFERENCES behaviors(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        start_idx integer NOT NULL,
        end_idx integer NOT NULL,
        confidence real NOT NULL DEFAULT 1,
        evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
        note text NOT NULL DEFAULT '',
        detector_version integer NOT NULL DEFAULT 1,
        source text NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'human')),
        review text CHECK (review IN ('confirmed', 'rejected')),
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK (end_idx >= start_idx),
        UNIQUE (behavior_id, trace_id, start_idx, end_idx)
    )""")
    op.execute(
        "CREATE INDEX behavior_hits_trend ON behavior_hits (owner_user_id, behavior_id, created_at)"
    )
    op.execute("CREATE INDEX behavior_hits_trace ON behavior_hits (trace_id)")

    # What each behavior has already looked at, so a growing trace costs only its
    # new segments and an edited behavior rescans from scratch (version bump).
    op.execute("""CREATE TABLE behavior_scans (
        behavior_id uuid NOT NULL REFERENCES behaviors(id) ON DELETE CASCADE,
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        behavior_version integer NOT NULL,
        fingerprint text NOT NULL,
        seen jsonb NOT NULL DEFAULT '[]'::jsonb,
        error text,
        scanned_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (behavior_id, trace_id)
    )""")

    op.execute("""CREATE TABLE behavior_alerts (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        behavior_id uuid NOT NULL REFERENCES behaviors(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        message text NOT NULL,
        stats jsonb NOT NULL DEFAULT '{}'::jsonb,
        delivered jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX behavior_alerts_owner ON behavior_alerts (owner_user_id, created_at DESC)"
    )

    op.execute("""CREATE TABLE rm_trace_segments (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        trace_id uuid NOT NULL REFERENCES rm_traces(id) ON DELETE CASCADE,
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        start_idx integer NOT NULL,
        end_idx integer NOT NULL,
        text text NOT NULL,
        content_hash text NOT NULL,
        embedding vector(384),
        embed_stale boolean NOT NULL DEFAULT true,
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (trace_id, start_idx)
    )""")
    op.execute("CREATE INDEX rm_trace_segments_owner ON rm_trace_segments (owner_user_id)")
    op.execute("CREATE INDEX rm_trace_segments_stale ON rm_trace_segments (id) WHERE embed_stale")
    op.execute(
        "CREATE INDEX rm_trace_segments_embedding ON rm_trace_segments "
        "USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )

    # Agent Judge investigations: the claims ledger, findings with step citations,
    # and cost, kept so a verdict can be inspected rather than taken on faith.
    op.execute("""CREATE TABLE agent_judge_reports (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        model_id uuid REFERENCES intuition_models(id) ON DELETE CASCADE,
        version_id uuid REFERENCES intuition_versions(id) ON DELETE SET NULL,
        trace_id uuid REFERENCES rm_traces(id) ON DELETE CASCADE,
        item_hash text NOT NULL,
        status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
        error text,
        report jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz
    )""")
    op.execute(
        "CREATE INDEX agent_judge_reports_trace ON agent_judge_reports (trace_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX agent_judge_reports_model ON agent_judge_reports (model_id, item_hash)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE agent_judge_reports")
    op.execute("DROP TABLE rm_trace_segments")
    op.execute("DROP TABLE behavior_alerts")
    op.execute("DROP TABLE behavior_scans")
    op.execute("DROP TABLE behavior_hits")
    op.execute("DROP TABLE behaviors")
