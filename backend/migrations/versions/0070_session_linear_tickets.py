"""Add extracted Linear ticket labels for sessions.

Revision ID: 0070
Revises: 0069
"""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS session_linear_tickets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_row_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            ticket_identifier TEXT NOT NULL,
            ticket_title TEXT,
            ticket_url TEXT,
            source TEXT NOT NULL,
            confidence REAL NOT NULL,
            linear_issue_id TEXT,
            ticket_status TEXT,
            ticket_assignee_name TEXT,
            ticket_team_key TEXT,
            ticket_team_name TEXT,
            ticket_project_name TEXT,
            linear_updated_at TIMESTAMPTZ,
            enriched_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (session_row_id, ticket_identifier),
            CHECK (source IN ('linear_preamble', 'linear_url', 'identifier')),
            CHECK (confidence >= 0 AND confidence <= 1)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_linear_tickets_workspace_identifier
        ON session_linear_tickets(workspace_id, ticket_identifier)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_linear_tickets_session
        ON session_linear_tickets(session_row_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_linear_tickets_enriched_at
        ON session_linear_tickets(enriched_at)
    """)

    op.execute(r"""
        WITH raw_candidates AS (
            SELECT
                s.workspace_id,
                s.id AS session_row_id,
                UPPER((ticket.parts)[2]) AS ticket_identifier,
                he.content,
                he.created_at
            FROM history_events he
            JOIN sessions s
              ON s.workspace_id = he.workspace_id
             AND s.session_id = he.session_id
            CROSS JOIN LATERAL regexp_matches(
                he.content,
                $$(?i)(You are working on a Linear ticket [`']?|Identifier:\s*|/issue/)([A-Z][A-Z0-9]+-\d+)$$,
                'g'
            ) AS ticket(parts)
            WHERE he.workspace_id IS NOT NULL
              AND he.session_id IS NOT NULL
              AND s.deleted_at IS NULL
        ),
        extracted AS (
            SELECT
                workspace_id,
                session_row_id,
                ticket_identifier,
                NULLIF(BTRIM((
                    regexp_match(
                        content,
                        '(?is)Identifier:\s*' || ticket_identifier || '\s+Title:\s*([^\r\n]+)'
                    )
                )[1]), '') AS ticket_title,
                NULLIF(BTRIM((
                    regexp_match(
                        content,
                        '(?i)(https?://linear\.app/[^[:space:]]*/issue/' || ticket_identifier || '[^[:space:]]*)'
                    )
                )[1]), '') AS ticket_url,
                CASE
                    WHEN content ~* ('You are working on a Linear ticket [`'']?' || ticket_identifier)
                      OR content ~* ('Identifier:\s*' || ticket_identifier)
                    THEN 'linear_preamble'
                    WHEN content ~* ('/issue/' || ticket_identifier)
                    THEN 'linear_url'
                    ELSE 'identifier'
                END AS source,
                CASE
                    WHEN content ~* ('You are working on a Linear ticket [`'']?' || ticket_identifier)
                      OR content ~* ('Identifier:\s*' || ticket_identifier)
                    THEN 1.0
                    WHEN content ~* ('/issue/' || ticket_identifier)
                    THEN 0.95
                    ELSE 0.85
                END AS confidence,
                created_at
            FROM raw_candidates
        ),
        ranked AS (
            SELECT DISTINCT ON (session_row_id, ticket_identifier)
                workspace_id,
                session_row_id,
                ticket_identifier,
                ticket_title,
                ticket_url,
                source,
                confidence
            FROM extracted
            ORDER BY
                session_row_id,
                ticket_identifier,
                (ticket_title IS NOT NULL) DESC,
                (ticket_url IS NOT NULL) DESC,
                confidence DESC,
                created_at ASC
        )
        INSERT INTO session_linear_tickets (
            workspace_id,
            session_row_id,
            ticket_identifier,
            ticket_title,
            ticket_url,
            source,
            confidence
        )
        SELECT
            workspace_id,
            session_row_id,
            ticket_identifier,
            ticket_title,
            ticket_url,
            source,
            confidence
        FROM ranked
        ON CONFLICT (session_row_id, ticket_identifier) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_linear_tickets CASCADE")
