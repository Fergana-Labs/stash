"""Pending share invites: share an object with an email that has no user yet.

`share_with_user_by_email` resolves the email to a user and writes a `shares`
row. When no user has that email, we stash the intent here instead of 404ing;
the row converts to a real share the moment a user with that email signs up
(password register or Auth0 first login).

Revision ID: 0085
Revises: 0084
"""

from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE share_invites (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            object_type   text NOT NULL,
            object_id     uuid NOT NULL,
            email         text NOT NULL,
            permission    text NOT NULL DEFAULT 'read',
            created_by    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at    timestamptz NOT NULL DEFAULT now(),
            UNIQUE (object_type, object_id, email)
        )
    """)
    # Conversion on signup looks invites up by the new user's email.
    op.execute("CREATE INDEX share_invites_email_idx ON share_invites (lower(email))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS share_invites")
