"""Keep developer read responses outside customer content and curation.

Revision ID: 0205
Revises: 0204
"""

from alembic import op

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE read_response_audits (
            id uuid PRIMARY KEY,
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            external_user_id text,
            session_id text,
            workflow_run_id text,
            method text NOT NULL,
            path text NOT NULL,
            request_data jsonb NOT NULL,
            status_code integer NOT NULL,
            response_body bytea NOT NULL,
            response_sha256 text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX read_response_audits_org_idx "
        "ON read_response_audits(workspace_id, external_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX read_response_audits_session_idx "
        "ON read_response_audits(workspace_id, session_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE read_response_audits")
