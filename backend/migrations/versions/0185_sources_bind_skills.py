"""A connected source can back skills directly.

Skills have until now been folders in the files tree, so a Google Doc could
only become one by being copied in. That copy is a second writer on content
whose truth lives upstream, and the copy has to be guarded against edits that
would silently diverge from Drive.

A source-backed skill removes the copy: `user_sources.binds_skills` marks a
picked Drive folder as a shelf, and every document sitting directly in it that
declares itself a skill — the same frontmatter block, checked by the same
validator, as any other SKILL.md — is read as one straight out of
`drive_documents`. Everything else on the shelf stays ordinary source material.
Sources are read-only in Stash, so divergence from Drive is unrepresentable
rather than merely guarded.

Membership stays explicit, the way 0181 made it: the flag is on the binding,
not on the presence of a file. A document disappearing upstream drops it from
the source listing and leaves the binding untouched — it can never silently
demote the shelf.

Revision ID: 0185
Revises: 0184
"""

from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_sources "
        "ADD COLUMN IF NOT EXISTS binds_skills BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_sources DROP COLUMN IF EXISTS binds_skills")
