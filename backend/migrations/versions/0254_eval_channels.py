"""Eval channels and rubric versions: evals that keep learning from what people drop in.

eval_messages is an eval's channel: people post text and files, and each file becomes an
example (intuition_examples.message_id), unlabeled until their words say good or bad. The
channel agent reads new messages (handled_at) and replies in threads (thread_id is the
top-level message) when it can't tell. intuition_models.channel_busy_since marks a running
agent so only one reads a channel at a time.

eval_rubric_versions keeps every rubric a judge eval has had: its traits, the reference
examples and description the judge reads with them, how it changed and why, and how well
it agreed with the labels. intuition_models.traits stays the current version's traits.

eval_grades caches the judge's grade of one example under one rubric (rubric_key hashes
everything the judge reads), so checking a rubric against new evidence grades only the
new examples.

Revision ID: 0254
Revises: 0253
"""

from alembic import op

revision = "0254"
down_revision = "0253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE eval_messages (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        thread_id uuid REFERENCES eval_messages(id) ON DELETE CASCADE,
        author text NOT NULL CHECK (author IN ('user', 'agent')),
        kind text NOT NULL DEFAULT 'message' CHECK (kind IN ('message', 'rubric')),
        text text NOT NULL DEFAULT '',
        data jsonb NOT NULL DEFAULT '{}'::jsonb,
        handled_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""")
    op.execute("CREATE INDEX eval_messages_model ON eval_messages(model_id, created_at)")
    op.execute(
        "CREATE INDEX eval_messages_unhandled ON eval_messages(model_id) "
        "WHERE author = 'user' AND handled_at IS NULL"
    )
    op.execute("""CREATE TABLE eval_rubric_versions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        number integer NOT NULL,
        traits jsonb NOT NULL,
        refs uuid[] NOT NULL DEFAULT '{}',
        instructions text NOT NULL DEFAULT '',
        source text NOT NULL CHECK (source IN ('written', 'revised', 'edited')),
        changes jsonb NOT NULL DEFAULT '[]'::jsonb,
        metrics jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (model_id, number)
    )""")
    op.execute("""CREATE TABLE eval_grades (
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        rubric_key text NOT NULL,
        example_id uuid NOT NULL REFERENCES intuition_examples(id) ON DELETE CASCADE,
        grade jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (model_id, rubric_key, example_id)
    )""")
    op.execute(
        "ALTER TABLE intuition_examples ADD COLUMN message_id uuid "
        "REFERENCES eval_messages(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX intuition_examples_message ON intuition_examples(message_id) "
        "WHERE message_id IS NOT NULL"
    )
    op.execute("ALTER TABLE intuition_models ADD COLUMN channel_busy_since timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE intuition_models DROP COLUMN channel_busy_since")
    op.execute("DROP INDEX intuition_examples_message")
    op.execute("ALTER TABLE intuition_examples DROP COLUMN message_id")
    op.execute("DROP TABLE eval_grades")
    op.execute("DROP TABLE eval_rubric_versions")
    op.execute("DROP TABLE eval_messages")
