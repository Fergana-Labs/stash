"""Released instruction snapshots and evidence of context delivery.

Revision ID: 0218
Revises: 0217
"""

from alembic import op

revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_wb_instruction_releases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            grader_id uuid NOT NULL REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
            change_id uuid REFERENCES rm_wb_changes(id),
            previous_change_id uuid REFERENCES rm_wb_changes(id),
            action text NOT NULL CHECK (action IN ('release', 'rollback', 'disable')),
            scope jsonb NOT NULL,
            content text,
            content_sha256 text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((action = 'disable' AND change_id IS NULL AND content IS NULL)
                OR (action <> 'disable' AND change_id IS NOT NULL AND content IS NOT NULL
                    AND content_sha256 IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE TABLE rm_wb_instruction_heads (
            grader_id uuid PRIMARY KEY REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
            release_id uuid NOT NULL REFERENCES rm_wb_instruction_releases(id)
        )
    """)
    op.execute("""
        CREATE TABLE rm_wb_instruction_deliveries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            grader_id uuid NOT NULL REFERENCES rm_wb_graders(id) ON DELETE CASCADE,
            release_id uuid NOT NULL REFERENCES rm_wb_instruction_releases(id),
            change_id uuid NOT NULL REFERENCES rm_wb_changes(id),
            session_id text NOT NULL,
            source_format text NOT NULL CHECK (source_format IN ('codex', 'claude_code')),
            repository text NOT NULL,
            content text NOT NULL,
            content_sha256 text NOT NULL,
            status text NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'captured')),
            trace_id uuid REFERENCES rm_traces(id) ON DELETE SET NULL,
            step_id uuid REFERENCES rm_trace_steps(id) ON DELETE SET NULL,
            offered_at timestamptz NOT NULL DEFAULT now(),
            captured_at timestamptz,
            UNIQUE (owner_user_id, session_id, grader_id)
        )
    """)
    op.execute("""
        CREATE INDEX rm_wb_instruction_deliveries_trace
            ON rm_wb_instruction_deliveries (trace_id)
    """)
    op.execute("""
        CREATE INDEX rm_wb_instruction_releases_owner
            ON rm_wb_instruction_releases (owner_user_id, grader_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE rm_wb_instruction_deliveries")
    op.execute("DROP TABLE rm_wb_instruction_heads")
    op.execute("DROP TABLE rm_wb_instruction_releases")
