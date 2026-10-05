"""Shared evaluator registry, permissioned corpus, and durable work queues.

Revision ID: 0215
Revises: 0214
"""

from alembic import op

revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE rm_reward_models ADD COLUMN scope text NOT NULL DEFAULT 'personal'
            CHECK (scope IN ('personal', 'shared'))
    """)
    op.execute("""
        ALTER TABLE rm_reward_models DROP CONSTRAINT rm_reward_models_trace_ids_check
    """)
    op.execute("""
        ALTER TABLE rm_reward_models ADD CONSTRAINT rm_reward_models_trace_scope_check CHECK (scope = 'shared' OR cardinality(trace_ids) > 0)
    """)
    op.execute("""
        ALTER TABLE rm_reward_models ADD COLUMN parent_model_id uuid REFERENCES rm_reward_models(id)
    """)
    op.execute("""
        ALTER TABLE rm_reward_models ADD COLUMN release_report jsonb
    """)
    op.execute("""
        ALTER TABLE rm_reward_models ADD COLUMN automatic_release boolean NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE rm_traces ADD COLUMN shared_training_allowed boolean NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE rm_traces ADD COLUMN learning_revision bigint NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE rm_scoring_runs ADD COLUMN automatic boolean NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE rm_scoring_runs ADD COLUMN trace_updated_at timestamptz
    """)
    op.execute("""
        CREATE TABLE rm_evaluator_registry (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            model_id uuid REFERENCES rm_reward_models(id),
            revision integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        INSERT INTO rm_evaluator_registry (singleton) VALUES (true)
    """)
    op.execute("""
        CREATE TABLE rm_evaluator_releases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            reward_model_id uuid NOT NULL REFERENCES rm_reward_models(id),
            previous_model_id uuid REFERENCES rm_reward_models(id),
            registry_revision integer NOT NULL UNIQUE,
            reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX rm_evaluator_released_model ON rm_evaluator_releases(reward_model_id)
    """)
    op.execute("""
        CREATE TABLE rm_task_partitions (
            task_group text PRIMARY KEY,
            partition text NOT NULL CHECK (partition IN ('train', 'eval'))
        )
    """)
    op.execute("""
        CREATE TABLE rm_evaluator_automation (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            enabled boolean NOT NULL DEFAULT false,
            owner_user_id uuid REFERENCES users(id),
            base_model text NOT NULL DEFAULT 'Qwen/Qwen3-0.6B',
            epochs integer NOT NULL DEFAULT 1,
            min_new_examples integer NOT NULL DEFAULT 100,
            interval_hours integer NOT NULL DEFAULT 24,
            auto_promote boolean NOT NULL DEFAULT false,
            last_attempt_at timestamptz,
            last_example_ids uuid[] NOT NULL DEFAULT '{}',
            error text
        )
    """)
    op.execute("""
        CREATE TABLE rm_training_examples (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            trace_id uuid REFERENCES rm_traces(id) ON DELETE CASCADE,
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            task_group text NOT NULL,
            domain text NOT NULL,
            agent text NOT NULL,
            partition text NOT NULL CHECK (partition IN ('train', 'eval')),
            pair jsonb NOT NULL,
            provenance jsonb NOT NULL,
            fingerprint text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX rm_training_examples_trace ON rm_training_examples(trace_id)
    """)
    op.execute("""
        CREATE TABLE rm_auto_scores (
            trace_id uuid PRIMARY KEY REFERENCES rm_traces(id) ON DELETE CASCADE,
            due_at timestamptz NOT NULL DEFAULT now(),
            attempts integer NOT NULL DEFAULT 0,
            error text
        )
    """)
    op.execute("""
        CREATE TABLE rm_example_collection (
            trace_id uuid PRIMARY KEY REFERENCES rm_traces(id) ON DELETE CASCADE,
            due_at timestamptz NOT NULL DEFAULT now(),
            status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            attempts integer NOT NULL DEFAULT 0,
            error text,
            started_at timestamptz
        )
    """)
    op.execute("""
        CREATE INDEX rm_auto_scores_due ON rm_auto_scores(due_at)
    """)
    op.execute("""
        CREATE INDEX rm_example_collection_due ON rm_example_collection(due_at)
    """)
    op.execute("""
        CREATE FUNCTION rm_trace_learning_changed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                INSERT INTO rm_auto_scores(trace_id, due_at) VALUES (NEW.id, now() + interval '30 seconds')
                ON CONFLICT(trace_id) DO UPDATE SET due_at = EXCLUDED.due_at, attempts = 0, error = NULL;
            END IF;
            DELETE FROM rm_training_examples WHERE trace_id = NEW.id;
            IF NEW.shared_training_allowed THEN
                INSERT INTO rm_example_collection(trace_id, due_at) VALUES (NEW.id, now() + interval '30 seconds')
                ON CONFLICT(trace_id) DO UPDATE SET due_at = EXCLUDED.due_at, status = 'queued', attempts = 0, error = NULL;
            ELSE
                DELETE FROM rm_example_collection WHERE trace_id = NEW.id;
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER rm_trace_learning_changed AFTER INSERT OR UPDATE OF updated_at, learning_revision, shared_training_allowed
            ON rm_traces FOR EACH ROW EXECUTE FUNCTION rm_trace_learning_changed()
    """)
    op.execute("""
        CREATE FUNCTION rm_annotation_learning_changed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                UPDATE rm_traces SET learning_revision = learning_revision + 1 WHERE id = OLD.trace_id;
                RETURN OLD;
            ELSE
                UPDATE rm_traces SET learning_revision = learning_revision + 1 WHERE id = NEW.trace_id;
                RETURN NEW;
            END IF;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER rm_annotation_learning_changed AFTER INSERT OR UPDATE OR DELETE
            ON rm_annotations FOR EACH ROW EXECUTE FUNCTION rm_annotation_learning_changed()
    """)
    op.execute("""
        INSERT INTO rm_auto_scores(trace_id) SELECT id FROM rm_traces
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER rm_annotation_learning_changed ON rm_annotations
    """)
    op.execute("""
        DROP FUNCTION rm_annotation_learning_changed()
    """)
    op.execute("""
        DROP TRIGGER rm_trace_learning_changed ON rm_traces
    """)
    op.execute("""
        DROP FUNCTION rm_trace_learning_changed()
    """)
    op.execute("""
        DROP TABLE rm_example_collection
    """)
    op.execute("""
        DROP TABLE rm_auto_scores
    """)
    op.execute("""
        DROP TABLE rm_training_examples
    """)
    op.execute("""
        DROP TABLE rm_task_partitions
    """)
    op.execute("""
        DROP TABLE rm_evaluator_automation
    """)
    op.execute("""
        DROP TABLE rm_evaluator_releases
    """)
    op.execute("""
        DROP TABLE rm_evaluator_registry
    """)
    op.execute("""
        ALTER TABLE rm_scoring_runs DROP COLUMN automatic, DROP COLUMN trace_updated_at
    """)
    op.execute("""
        ALTER TABLE rm_traces DROP COLUMN shared_training_allowed, DROP COLUMN learning_revision
    """)
    op.execute("""
        ALTER TABLE rm_reward_models DROP COLUMN release_report, DROP COLUMN parent_model_id, DROP COLUMN automatic_release
    """)
    op.execute("""
        ALTER TABLE rm_reward_models DROP CONSTRAINT rm_reward_models_trace_scope_check
    """)
    op.execute("""
        DELETE FROM rm_reward_models WHERE scope = 'shared'
    """)
    op.execute("""
        ALTER TABLE rm_reward_models DROP COLUMN scope
    """)
    op.execute("""
        ALTER TABLE rm_reward_models ADD CONSTRAINT rm_reward_models_trace_ids_check CHECK (cardinality(trace_ids) > 0)
    """)
