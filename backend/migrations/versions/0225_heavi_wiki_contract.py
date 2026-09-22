"""Keep Heavi's deployed developer integration on its existing wiki contract."""

from alembic import op

revision = "0225"
down_revision = "0224"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN legacy_wiki_enabled boolean NOT NULL DEFAULT false"
    )
    op.execute("""
        UPDATE workspaces w SET legacy_wiki_enabled=true
        WHERE w.external_skill_folder_id IS NOT NULL AND (
            w.domain='heaviai.com'
            OR w.created_by IN (SELECT id FROM users WHERE lower(email)='stash@heaviai.com')
            OR w.scope_user_id IN (SELECT id FROM users WHERE lower(email)='stash@heaviai.com')
        )
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE workspaces DROP COLUMN legacy_wiki_enabled")
