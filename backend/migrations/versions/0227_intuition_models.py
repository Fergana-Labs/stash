"""Intuition models: a trainable wrapper around a Jev-style judge.

A version freezes everything that shapes a prediction (description, output
labels, rubric questions, seed examples, provider and head weights). Rubric
answers are cached per (item, question context) so editing one question only
regrades that question, and refitting the head never calls the provider.

Revision ID: 0227
Revises: 0226
"""

from alembic import op

revision = "0227"
down_revision = "0226"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE intuition_models (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
        output_type text NOT NULL CHECK (output_type IN ('choice', 'preference')),
        active_version_id uuid,
        draft_version_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX intuition_models_owner ON intuition_models(owner_user_id)")
    op.execute("""CREATE TABLE intuition_versions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        number integer NOT NULL,
        status text NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
        description text NOT NULL DEFAULT '',
        labels jsonb NOT NULL DEFAULT '[]',
        rubric jsonb NOT NULL DEFAULT '[]',
        seed_example_ids uuid[] NOT NULL DEFAULT '{}',
        provider text NOT NULL,
        provider_model text NOT NULL,
        head jsonb,
        metrics jsonb,
        gate jsonb,
        parent_version_id uuid REFERENCES intuition_versions(id) ON DELETE SET NULL,
        promoted_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (model_id, number)
    )""")
    op.execute("""ALTER TABLE intuition_models
        ADD CONSTRAINT intuition_models_active_fk FOREIGN KEY (active_version_id)
            REFERENCES intuition_versions(id) ON DELETE SET NULL,
        ADD CONSTRAINT intuition_models_draft_fk FOREIGN KEY (draft_version_id)
            REFERENCES intuition_versions(id) ON DELETE SET NULL""")
    op.execute("""CREATE TABLE intuition_examples (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        kind text NOT NULL CHECK (kind IN ('item', 'pair')),
        -- json, not jsonb: keeps the user's key order for display.
        item json NOT NULL,
        item_b json,
        label text,
        source text NOT NULL CHECK (source IN ('human', 'agent', 'generated', 'production')),
        split text NOT NULL CHECK (split IN ('train', 'eval')),
        needs_review boolean NOT NULL DEFAULT false,
        note text NOT NULL DEFAULT '',
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK ((kind = 'pair') = (item_b IS NOT NULL))
    )""")
    op.execute("CREATE INDEX intuition_examples_model ON intuition_examples(model_id, created_at)")
    # Production calls are logged; a reviewed call becomes a 'production' example.
    op.execute("""CREATE TABLE intuition_predictions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        version_id uuid NOT NULL REFERENCES intuition_versions(id) ON DELETE CASCADE,
        kind text NOT NULL CHECK (kind IN ('predict', 'compare')),
        input json NOT NULL,
        output jsonb NOT NULL,
        confidence double precision,
        caller text NOT NULL,
        status text NOT NULL DEFAULT 'unreviewed'
            CHECK (status IN ('unreviewed', 'labeled', 'dismissed')),
        example_id uuid REFERENCES intuition_examples(id) ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX intuition_predictions_model ON intuition_predictions(model_id, created_at DESC)"
    )
    op.execute("""CREATE TABLE intuition_grades (
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        grade_key text NOT NULL,
        answer jsonb NOT NULL,
        provider text NOT NULL,
        provider_model text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (model_id, grade_key)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE intuition_grades")
    op.execute("DROP TABLE intuition_predictions")
    op.execute("DROP TABLE intuition_examples")
    op.execute("ALTER TABLE intuition_models DROP CONSTRAINT intuition_models_active_fk")
    op.execute("ALTER TABLE intuition_models DROP CONSTRAINT intuition_models_draft_fk")
    op.execute("DROP TABLE intuition_versions")
    op.execute("DROP TABLE intuition_models")
