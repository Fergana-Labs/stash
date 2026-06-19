"""Add canvases: agent-generated generative-UI artifacts.

A canvas is the right-hand panel the agent renders beside the chat — a title
plus an ordered list of UI blocks (pre-built components or raw HTML). Canvases
are workspace objects so a generated view can be reopened and refined over time.
`session_id` links a canvas back to the chat that produced it.

Revision ID: 0118
Revises: 0117
"""

from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None

_COLUMNS = """
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    session_id   text,
    title        text NOT NULL,
    blocks       jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by   uuid NOT NULL,
    updated_by   uuid,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
"""


def upgrade() -> None:
    op.execute(f"CREATE TABLE canvases ({_COLUMNS})")
    op.execute(
        "CREATE INDEX canvases_workspace_updated_idx "
        "ON canvases (workspace_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX canvases_session_idx ON canvases (workspace_id, session_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canvases")
