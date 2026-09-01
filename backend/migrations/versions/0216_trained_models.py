"""Trained models and the one-time purchases that pay for training them.

A trained model is something a user owns forever: an adapter fitted on their
own material by a GPU job, then used without limit. `kind` names which
recipe produced it (only "stylewriter" today) so the next train-a-model skill
adds a kind, not a table.

A purchase is one paid training run. Stripe Checkout in payment mode creates
it via webhook; the unique session id makes repeated webhook deliveries
harmless. Queuing a training run consumes it (`consumed_by`); a run that
fails clears that again so the money is not lost.

Revision ID: 0216
Revises: 0202
"""

from alembic import op

revision = "0216"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE training_purchases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind text NOT NULL,
            stripe_session_id text NOT NULL UNIQUE,
            amount_cents integer NOT NULL,
            consumed_by uuid,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_training_purchases_spendable "
        "ON training_purchases (owner_user_id, kind) WHERE consumed_by IS NULL"
    )
    op.execute(
        """
        CREATE TABLE trained_models (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind text NOT NULL,
            name text NOT NULL,
            status text NOT NULL,
            purchase_id uuid REFERENCES training_purchases(id),
            corpus_folder_id uuid REFERENCES folders(id) ON DELETE SET NULL,
            corpus jsonb NOT NULL,
            words integer NOT NULL,
            base_model text NOT NULL,
            job_ref text,
            provider_ref text,
            profile jsonb,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            trained_at timestamptz,
            UNIQUE (owner_user_id, kind, name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trained_models")
    op.execute("DROP TABLE IF EXISTS training_purchases")
