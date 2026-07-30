"""Add scope_signature to embedding_projections so user-wide rows can cache.

The workspace removal (#667) turned the memory viewer's projection request
into a user-wide one (owner_user_id NULL), and user-wide results were
excluded from the embedding_projections cache because they depend on which
other users' content the requester can currently access — a cached row could
keep serving someone's content after a share is revoked. The cost was that
every memory-page load refit UMAP inline (~a minute cold).

scope_signature is a hash of the scope-owner ids the user can access at
compute time. A user-wide cache row is served only while the stored signature
matches the requester's current one, so access changes invalidate it
immediately and the cache becomes safe to use. Explicit-scope rows keep a
NULL signature; their behavior is unchanged.

Existing rows are all explicit-scope (user-wide rows were never written), so
NULL is already correct for them and no data migration is needed.

Revision ID: 0178
Revises: 0177
"""

from alembic import op

revision = "0178"
down_revision = "0177"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE embedding_projections ADD COLUMN IF NOT EXISTS scope_signature TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE embedding_projections DROP COLUMN IF EXISTS scope_signature")
