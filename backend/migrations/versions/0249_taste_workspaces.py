"""Owner-scoped taste workspaces, durable jobs, reviews, and runtime receipts."""

from alembic import op

revision = "0249"
down_revision = "0248"
branch_labels = None
depends_on = None


def upgrade():
    statements = """
    CREATE TABLE taste_workspaces (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      owner_user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      name text NOT NULL DEFAULT 'My website taste',
      config jsonb NOT NULL DEFAULT '{}',
      reviews jsonb NOT NULL DEFAULT '{}',
      revision integer NOT NULL DEFAULT 0,
      fitted_revision integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE taste_jobs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES taste_workspaces(id) ON DELETE CASCADE,
      operation text NOT NULL,
      input jsonb NOT NULL DEFAULT '{}',
      status text NOT NULL DEFAULT 'queued',
      progress text NOT NULL DEFAULT 'Waiting for worker',
      result jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX taste_one_job ON taste_jobs(workspace_id)
      WHERE status IN ('queued','running');
    CREATE TABLE taste_predictions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES taste_workspaces(id) ON DELETE CASCADE,
      version text NOT NULL,
      input jsonb NOT NULL,
      output jsonb NOT NULL,
      feedback text,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    """
    for statement in statements.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for table in ("taste_predictions", "taste_jobs", "taste_workspaces"):
        op.drop_table(table)
