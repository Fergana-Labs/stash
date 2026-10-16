"""Model wizard: embedding probes as rubric signals, and wizard chat sessions.

Revision ID: 0242
Revises: 0241
"""

from alembic import op

revision = "0242"
down_revision = "0241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A probe is a ridge readout over item embeddings, fitted on one snapshot of
    # labeled training examples. A `probe` rubric question pins one by id, so the
    # judge-answer cache never mixes answers from different fits. `loo` holds the
    # leave-one-out answer for each training item, keyed by item hash, so the head
    # stacked on top never sees a probe answer that memorized the item's label.
    op.execute("""CREATE TABLE intuition_probes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        model_id uuid NOT NULL REFERENCES intuition_models(id) ON DELETE CASCADE,
        embedder text NOT NULL,
        dims integer NOT NULL,
        classes jsonb NOT NULL,
        weights jsonb NOT NULL,
        scale double precision NOT NULL,
        loo jsonb NOT NULL DEFAULT '{}'::jsonb,
        metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX intuition_probes_model ON intuition_probes(model_id, created_at)")

    # A wizard session is one guided conversation that builds (at most) one model.
    # `messages` is the Claude transcript; `transcript` is what the chat renders,
    # including the interactive cards the wizard opened.
    op.execute("""CREATE TABLE intuition_wizard_sessions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        model_id uuid REFERENCES intuition_models(id) ON DELETE SET NULL,
        title text NOT NULL DEFAULT 'New model',
        messages jsonb NOT NULL DEFAULT '[]'::jsonb,
        transcript jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX intuition_wizard_sessions_owner "
        "ON intuition_wizard_sessions(owner_user_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intuition_wizard_sessions")
    op.execute("DROP TABLE IF EXISTS intuition_probes")
