"""Image evals: learn what one person likes from example images, score new ones.

A classifier is a logistic head over frozen image embeddings. Examples keep their
embedding so retraining never re-embeds; every scoring call is logged with its
image, score and written comments, and a person can label a call to turn it into
a new example. Building a classifier also writes a style brief from the liked
examples and adds imitations of them as disliked examples (source 'imitation'),
so the score measures "indistinguishable from the real thing" rather than
"better than generic images".

model_id links an image eval made in the eval wizard to its intuition_models row,
so it is listed with the other evals and the wizard can resume it.

An uploaded example's embedding is NULL until the next build or training run
embeds it, so uploads return without waiting on the GPU.

Revision ID: 0250
Revises: 0249
"""

from alembic import op

revision = "0250"
down_revision = "0249"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE image_evals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        model_id uuid UNIQUE REFERENCES intuition_models(id) ON DELETE SET NULL,
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
        description text NOT NULL DEFAULT '',
        embed_model text NOT NULL,
        style_brief text NOT NULL DEFAULT '',
        build jsonb,
        head jsonb,
        metrics jsonb,
        trained_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX image_evals_owner ON image_evals(owner_user_id)")
    op.execute("""CREATE TABLE image_eval_calls (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        classifier_id uuid NOT NULL REFERENCES image_evals(id) ON DELETE CASCADE,
        caller text NOT NULL DEFAULT '',
        task text NOT NULL DEFAULT '',
        image_key text NOT NULL,
        content_type text NOT NULL,
        embedding real[] NOT NULL,
        score real NOT NULL,
        comments jsonb,
        trained_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX image_eval_calls_classifier ON image_eval_calls(classifier_id, created_at DESC)"
    )
    op.execute("""CREATE TABLE image_eval_examples (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        classifier_id uuid NOT NULL REFERENCES image_evals(id) ON DELETE CASCADE,
        label text NOT NULL CHECK (label IN ('liked', 'disliked')),
        source text NOT NULL CHECK (source IN ('upload', 'call', 'imitation')),
        call_id uuid UNIQUE REFERENCES image_eval_calls(id) ON DELETE SET NULL,
        filename text NOT NULL DEFAULT '',
        note text NOT NULL DEFAULT '',
        image_key text NOT NULL,
        content_type text NOT NULL,
        embedding real[],
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE INDEX image_eval_examples_classifier ON image_eval_examples(classifier_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE image_eval_examples")
    op.execute("DROP TABLE image_eval_calls")
    op.execute("DROP TABLE image_evals")
