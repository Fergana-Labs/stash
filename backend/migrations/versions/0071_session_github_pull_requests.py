"""Track session links to GitHub pull requests.

Revision ID: 0071
Revises: 0070
"""

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE session_linear_tickets
        DROP CONSTRAINT IF EXISTS session_linear_tickets_source_check
    """)
    op.execute("""
        ALTER TABLE session_linear_tickets
        ADD CONSTRAINT session_linear_tickets_source_check
        CHECK (source IN (
            'linear_preamble',
            'linear_url',
            'identifier',
            'github_pr_branch',
            'github_pr_title',
            'github_pr_body',
            'github_pr_commit'
        ))
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS session_github_pull_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_row_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            pull_number INTEGER NOT NULL,
            pull_url TEXT NOT NULL,
            pull_title TEXT,
            head_ref TEXT,
            fetched_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (session_row_id, owner, repo, pull_number),
            CHECK (pull_number > 0)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_github_pull_requests_workspace
        ON session_github_pull_requests(workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_github_pull_requests_session
        ON session_github_pull_requests(session_row_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_github_pull_requests CASCADE")
    op.execute("DELETE FROM session_linear_tickets WHERE source LIKE 'github_pr_%'")
    op.execute("""
        ALTER TABLE session_linear_tickets
        DROP CONSTRAINT IF EXISTS session_linear_tickets_source_check
    """)
    op.execute("""
        ALTER TABLE session_linear_tickets
        ADD CONSTRAINT session_linear_tickets_source_check
        CHECK (source IN ('linear_preamble', 'linear_url', 'identifier'))
    """)
