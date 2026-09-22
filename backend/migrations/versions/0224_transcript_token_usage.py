"""Replace trace quotas with durable transcript-token accounting."""

from alembic import op

revision = "0224"
down_revision = "0223"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
        CREATE FUNCTION transcript_usage_key(session_id text, event_type text, content text)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT encode(digest(jsonb_build_array(session_id,event_type,content)::text,
                                 'sha256'), 'hex')
        $$
    """)
    op.execute("""
        CREATE TABLE transcript_usage (
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content_key text NOT NULL,
            tokens bigint NOT NULL CHECK (tokens >= 0),
            processed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (owner_user_id, content_key)
        )
    """)
    op.execute("""
        CREATE INDEX transcript_usage_month ON transcript_usage(owner_user_id, processed_at)
    """)
    op.execute("""
        ALTER TABLE user_subscriptions
            ADD COLUMN overage_limit_cents integer NOT NULL DEFAULT 0 CHECK (overage_limit_cents >= 0),
            ADD COLUMN stripe_subscription_created bigint NOT NULL DEFAULT 0,
            ADD COLUMN usage_item_id text
    """)
    op.execute("""
        CREATE TABLE curation_batches (
            owner_user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            events jsonb NOT NULL,
            has_more boolean NOT NULL,
            expires_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE transcript_meter_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            customer_id text NOT NULL,
            tokens bigint NOT NULL CHECK (tokens > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            first_attempt_at timestamptz,
            last_attempt_at timestamptz,
            reported_at timestamptz,
            error text
        )
    """)
    op.execute("""
        CREATE INDEX transcript_meter_pending ON transcript_meter_events(created_at)
            WHERE reported_at IS NULL;
    """)
    # Existing knowledge is carried forward without a retrospective bill. Keys survive
    # transcript replacement/deletion; importing the same content cannot charge again.
    op.execute("""
        INSERT INTO transcript_usage(owner_user_id,content_key,tokens)
        SELECT DISTINCT he.owner_user_id,
            transcript_usage_key(he.session_id,he.event_type,he.content), 0
        FROM history_events he JOIN sessions s ON s.owner_user_id=he.owner_user_id AND s.session_id=he.session_id
        WHERE he.session_id IS NOT NULL AND he.session_id NOT LIKE 'agent-curate-%'
          AND EXISTS (SELECT 1 FROM agents a WHERE a.user_id=he.owner_user_id
                      AND a.is_curator AND he.created_at<=a.curated_through
                      AND (a.curator_skill='external')=(s.end_user_id IS NOT NULL))
        ON CONFLICT DO NOTHING
    """)

    op.execute("ALTER TABLE sessions DROP COLUMN curated_at")


def downgrade() -> None:
    raise NotImplementedError("Restore a database backup to reverse token accounting.")
