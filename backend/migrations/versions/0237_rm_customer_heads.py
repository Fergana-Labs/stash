"""Private customer heads pinned to a released shared basis and cached inputs."""

from alembic import op

revision = "0237"
down_revision = "0236"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE rm_customer_feature_pairs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        shared_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        feature_version text NOT NULL CHECK (length(feature_version)=64),
        manifest_digest text NOT NULL CHECK (length(manifest_digest)=64),
        context_digest text NOT NULL CHECK (length(context_digest)=64),
        input_a_digest text NOT NULL CHECK (length(input_a_digest)=64),
        input_b_digest text NOT NULL CHECK (length(input_b_digest)=64),
        provenance_digest text NOT NULL CHECK (length(provenance_digest)=64),
        features_a jsonb NOT NULL,
        features_b jsonb NOT NULL,
        trace_id uuid REFERENCES rm_traces(id) ON DELETE CASCADE,
        trace_updated_at timestamptz,
        label integer CHECK (label IN (-1,1)),
        label_source text CHECK (label_source IN ('human','operator_verified')),
        label_reference text,
        revision integer NOT NULL DEFAULT 0,
        revoked boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK ((trace_id IS NULL) = (trace_updated_at IS NULL)),
        CHECK ((label IS NULL) = (label_source IS NULL)),
        UNIQUE(owner_user_id,shared_model_id,manifest_digest,context_digest,input_a_digest,input_b_digest,provenance_digest)
    )""")
    op.execute(
        "CREATE INDEX rm_customer_feature_pairs_owner ON rm_customer_feature_pairs(owner_user_id)"
    )
    op.execute("""CREATE TABLE rm_customer_heads (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        shared_model_id uuid NOT NULL REFERENCES rm_reward_models(id) ON DELETE CASCADE,
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
        version integer NOT NULL,
        feature_version text NOT NULL,
        manifest_digest text NOT NULL,
        head jsonb NOT NULL,
        example_snapshot jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(owner_user_id,shared_model_id,name,version)
    )""")
    op.execute(
        "CREATE INDEX rm_customer_heads_owner ON rm_customer_heads(owner_user_id,created_at)"
    )


def downgrade():
    op.execute("DROP TABLE rm_customer_heads")
    op.execute("DROP TABLE rm_customer_feature_pairs")
