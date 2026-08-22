"""Developer platform: orgs, invite-only workspaces, external wiki.

External Multiplayer lets a developer (e.g. Heavi) run Stash for *their*
customers: each customer is an `orgs` row under the developer's workspace,
sessions and files carry an `org_id`, and the workspace curator distills an
anonymized cross-org wiki plus a per-org notepad.

Workspace changes that make this possible:
- `domain` becomes nullable. A NULL-domain workspace has no derived
  membership — only explicit `workspace_members` rows — which is what allows
  one-man developer workspaces on shared email domains. The membership
  predicate already fails closed on NULL.
- `created_by` records the workspace owner (admin-provisioned rows keep NULL).
- `external_wiki_folder_id` is the wiki the external curator writes; it doubles
  as the "developer platform is active" marker for a workspace.

Org identity is the developer's own id (`external_id`), asserted by their
backend on every call — Stash isolates between developers, not between one
developer's orgs. Each org owns a notepad folder (`notepad_folder_id`) for
non-anonymized per-org memory.

Revision ID: 0189
Revises: 0188
"""

from alembic import op

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ALTER COLUMN domain DROP NOT NULL")
    op.execute("ALTER TABLE workspaces ADD COLUMN created_by UUID REFERENCES users(id)")
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN external_wiki_folder_id UUID REFERENCES folders(id)"
    )
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN org_notepads_folder_id UUID REFERENCES folders(id)"
    )
    op.execute(
        """
        CREATE TABLE orgs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            external_id VARCHAR(128) NOT NULL,
            name TEXT NOT NULL,
            share_wiki BOOLEAN NOT NULL DEFAULT true,
            notepad_folder_id UUID NOT NULL REFERENCES folders(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, external_id)
        )
        """
    )
    op.execute("ALTER TABLE sessions ADD COLUMN org_id UUID REFERENCES orgs(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_sessions_org ON sessions (org_id) WHERE org_id IS NOT NULL")
    op.execute("ALTER TABLE files ADD COLUMN org_id UUID REFERENCES orgs(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_files_org ON files (org_id) WHERE org_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_org")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS org_id")
    op.execute("DROP INDEX IF EXISTS idx_sessions_org")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS org_id")
    op.execute("DROP TABLE IF EXISTS orgs")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS org_notepads_folder_id")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS external_wiki_folder_id")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE workspaces ALTER COLUMN domain SET NOT NULL")
