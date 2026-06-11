"""Security audit events for sensitive integration/source actions.

Revision ID: 0104
Revises: 0103
"""

from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE security_audit_events (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id    uuid REFERENCES workspaces(id) ON DELETE CASCADE,
            actor_user_id   uuid REFERENCES users(id) ON DELETE SET NULL,
            action          text NOT NULL,
            target_type     text NOT NULL,
            target_id       text,
            provider        text,
            source_type     text,
            metadata        jsonb NOT NULL DEFAULT '{}',
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX security_audit_events_workspace_idx "
        "ON security_audit_events(workspace_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX security_audit_events_actor_idx "
        "ON security_audit_events(actor_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX security_audit_events_action_idx "
        "ON security_audit_events(action, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS security_audit_events")
