"""Pages can belong to an org.

An org is "its own pile of files and sessions", and its memory is a pile of
pages: the per-org notepad the curator writes. Those pages were identified
only by which folder they sat in, so nothing on the row said which customer a
page was about — a page moved out of the notepad folder silently lost its
customer.

`org_id` makes that explicit and independent of placement. It does not
replace folder placement as the answer to *which wiki* a page belongs to:
the shared external wiki is `workspaces.external_wiki_folder_id`, the
internal team wiki is the scope's Memory folder, and a page's audience is
still the folder it lives in. This column answers a different question —
whose material is this.

ON DELETE CASCADE, matching sources and for the same reason: a page holding
one customer's non-anonymized detail must not survive that org as an
ownerless page in the workspace.

Revision ID: 0192
Revises: 0191
"""

from alembic import op

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pages ADD COLUMN org_id UUID REFERENCES orgs(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX idx_pages_org ON pages (org_id) WHERE org_id IS NOT NULL")
    # Pages already sitting in an org's notepad folder belong to that org.
    op.execute(
        """
        UPDATE pages p SET org_id = o.id
        FROM orgs o
        WHERE p.folder_id = o.notepad_folder_id AND p.org_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pages_org")
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS org_id")
