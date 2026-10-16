"""Judge curation: eval briefs, triage, calibration ratings, review links, topics.

Revision ID: 0243
Revises: 0242
"""

from alembic import op

revision = "0243"
down_revision = "0242"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The eval brief is what the wizard elicited about the decision (who makes it,
    # what an input is, label boundaries, costly mistakes, must-never cases). It is
    # not versioned: it describes the task, while versions describe a judge of it.
    op.execute("ALTER TABLE intuition_models ADD COLUMN brief jsonb NOT NULL DEFAULT '{}'::jsonb")
    # What the wizard learns before the model exists waits on the session.
    op.execute(
        "ALTER TABLE intuition_wizard_sessions ADD COLUMN brief jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    # Topics cluster recent traffic and examples; recomputed on demand.
    op.execute("ALTER TABLE intuition_models ADD COLUMN topics jsonb")

    # Triage: "needs review" escalates a prediction to the expert queue.
    op.execute(
        "ALTER TABLE intuition_predictions DROP CONSTRAINT intuition_predictions_status_check"
    )
    op.execute(
        "ALTER TABLE intuition_predictions ADD CONSTRAINT intuition_predictions_status_check "
        "CHECK (status IN ('unreviewed', 'escalated', 'labeled', 'dismissed'))"
    )
    op.execute(
        "ALTER TABLE intuition_predictions ADD COLUMN escalation_note text NOT NULL DEFAULT ''"
    )

    # Calibration: several people label the same examples, blind to each other.
    op.execute(
        "ALTER TABLE intuition_examples ADD COLUMN calibration boolean NOT NULL DEFAULT false"
    )
    op.execute("""CREATE TABLE intuition_review_links (
        token text PRIMARY KEY,
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        reviewer text NOT NULL CHECK (length(reviewer) BETWEEN 1 AND 80),
        revoked boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX intuition_review_links_model ON intuition_review_links(model_id)")
    # `rater` is 'owner' for the model owner's own labels (mirrored from the
    # example), or the review link's token for an invited reviewer.
    op.execute("""CREATE TABLE intuition_ratings (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        example_id uuid NOT NULL REFERENCES intuition_examples(id) ON DELETE CASCADE,
        rater text NOT NULL,
        label text NOT NULL,
        note text NOT NULL DEFAULT '',
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (example_id, rater)
    )""")
    op.execute("CREATE INDEX intuition_ratings_model ON intuition_ratings(model_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intuition_ratings")
    op.execute("DROP TABLE IF EXISTS intuition_review_links")
    op.execute("ALTER TABLE intuition_examples DROP COLUMN calibration")
    op.execute("ALTER TABLE intuition_predictions DROP COLUMN escalation_note")
    op.execute("UPDATE intuition_predictions SET status = 'unreviewed' WHERE status = 'escalated'")
    op.execute(
        "ALTER TABLE intuition_predictions DROP CONSTRAINT intuition_predictions_status_check"
    )
    op.execute(
        "ALTER TABLE intuition_predictions ADD CONSTRAINT intuition_predictions_status_check "
        "CHECK (status IN ('unreviewed', 'labeled', 'dismissed'))"
    )
    op.execute("ALTER TABLE intuition_wizard_sessions DROP COLUMN brief")
    op.execute("ALTER TABLE intuition_models DROP COLUMN topics")
    op.execute("ALTER TABLE intuition_models DROP COLUMN brief")
