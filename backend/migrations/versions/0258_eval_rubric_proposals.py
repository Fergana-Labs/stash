"""Reviewed rubric changes: an eval can require approval before its rubric changes.

intuition_models.review_required turns it on. Then a build, a rewrite, or a person's edit
no longer saves a new rubric version; it saves a row in eval_rubric_proposals: the rubric it
would become (traits, refs, instructions, scoring), the version it was proposed on (base),
what changed and why, and checks: agreement with the labels before and after, the examples
it fixes and breaks, how recent agent calls would score, and the manipulation check.
Approving one saves it as the next rubric version; rejecting one keeps the rubric as it is
and tells later builds not to propose the same edit.

eval_rubric_versions.created_by is the person who edited the rubric directly, and
proposal_id the approved proposal a version came from (its approver is on the proposal).

Revision ID: 0258
Revises: 0257
"""

from alembic import op

revision = "0258"
down_revision = "0257"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE intuition_models ADD COLUMN review_required boolean NOT NULL DEFAULT false"
    )
    op.execute("""CREATE TABLE eval_rubric_proposals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        number integer NOT NULL,
        base integer NOT NULL,
        traits jsonb NOT NULL,
        refs uuid[] NOT NULL DEFAULT '{}',
        instructions text NOT NULL DEFAULT '',
        scoring text NOT NULL DEFAULT 'mean' CHECK (scoring IN ('mean', 'lowest')),
        source text NOT NULL CHECK (source IN ('written', 'revised', 'edited')),
        changes jsonb NOT NULL DEFAULT '[]'::jsonb,
        checks jsonb,
        status text NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'approved', 'rejected', 'replaced')),
        proposed_by uuid REFERENCES users(id) ON DELETE SET NULL,
        thread_id uuid REFERENCES eval_messages(id) ON DELETE SET NULL,
        decided_by uuid REFERENCES users(id) ON DELETE SET NULL,
        decided_at timestamptz,
        note text NOT NULL DEFAULT '',
        version integer,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (model_id, number)
    )""")
    op.execute("""
        ALTER TABLE eval_rubric_versions
            ADD COLUMN created_by uuid REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN proposal_id uuid REFERENCES eval_rubric_proposals(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE eval_rubric_versions DROP COLUMN proposal_id, DROP COLUMN created_by")
    op.execute("DROP TABLE eval_rubric_proposals")
    op.execute("ALTER TABLE intuition_models DROP COLUMN review_required")
