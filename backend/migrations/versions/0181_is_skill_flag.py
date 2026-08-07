"""Skill membership becomes a stored flag instead of a derived property.

A folder was a skill because it contained a live SKILL.md. That made
membership change as a side effect of ordinary file edits: deleting the
file silently demoted the skill (a customer hit this three times in two
weeks, losing their skill from every agent's catalog with no warning), and
dropping a stray SKILL.md into Memory silently promoted it.

Membership is now explicit: folders.is_skill, flipped only by deliberate
verbs. Content stays exactly where it was — SKILL.md remains the one truth
for instructions and frontmatter metadata.

Backfill flags every folder that has a live SKILL.md today, so no skill
disappears. Protected folders (Memory, Clips) are excluded and can never be
flagged: the constraint makes the promote-Memory-then-wipe-it path
unrepresentable rather than merely guarded.

Revision ID: 0181
Revises: 0180
"""

from alembic import op

revision = "0181"
down_revision = "0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE folders ADD COLUMN IF NOT EXISTS is_skill BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("""
UPDATE folders f SET is_skill = true
WHERE NOT f.is_protected
  AND EXISTS (
    SELECT 1 FROM pages p
    WHERE p.folder_id = f.id AND p.name = 'SKILL.md' AND p.deleted_at IS NULL
  )
""")
    op.execute(
        "ALTER TABLE folders ADD CONSTRAINT folders_protected_is_never_a_skill "
        "CHECK (NOT (is_skill AND is_protected))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_folders_is_skill ON folders(owner_user_id) WHERE is_skill"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_folders_is_skill")
    op.execute("ALTER TABLE folders DROP CONSTRAINT IF EXISTS folders_protected_is_never_a_skill")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS is_skill")
