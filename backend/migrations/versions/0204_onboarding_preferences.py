"""Web-onboarding choices the CLI applies at signin.

One row per user: the setup decisions made on the web onboarding page
(which agents to record, folder scope, history import, CLAUDE.md opt-in).
`consumed_at` is stamped by the CLI once it applies them, so a later
standalone signin runs the wizard instead of re-applying stale choices.

Revision ID: 0204
Revises: 0203
"""

from alembic import op

revision = "0204"
down_revision = "0203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE onboarding_preferences (
            user_id          uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            enabled_agents   text[] NOT NULL,
            record_scope     text NOT NULL
                             CHECK (record_scope IN ('everything', 'selected_folders')),
            import_history   boolean NOT NULL,
            claude_md_opt_in boolean NOT NULL,
            updated_at       timestamptz NOT NULL DEFAULT now(),
            consumed_at      timestamptz
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS onboarding_preferences")
