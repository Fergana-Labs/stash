"""AI-curated skills: three reserved slots the nightly curator owns.

The curator already compiles the user's activity into the Memory wiki. The
wiki is pull — it helps only when an agent thinks to search it. Skills are
push: every SKILL.md description is loaded at session start, so a curated
skill fires without the agent knowing to look.

Curated skills are ordinary skill folders (same ``is_skill`` flag, same
sync, same Skills surface) marked ``is_curated`` so two things are
expressible: the three-slot cap, and adoption — a human edit clears the flag
and the curator may never touch that skill again.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN is_curated boolean NOT NULL DEFAULT false")
    # A curated folder is always a skill, so the existing
    # folders_protected_is_never_a_skill check keeps Memory and Clips out too.
    op.execute(
        "ALTER TABLE folders ADD CONSTRAINT folders_curated_is_a_skill "
        "CHECK (NOT is_curated OR is_skill)"
    )
    op.execute("CREATE INDEX idx_folders_is_curated ON folders(owner_user_id) WHERE is_curated")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_folders_is_curated")
    op.execute("ALTER TABLE folders DROP CONSTRAINT IF EXISTS folders_curated_is_a_skill")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS is_curated")
