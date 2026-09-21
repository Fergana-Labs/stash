"""Record when each useful session trace was curated."""

from alembic import op

revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN curated_at timestamptz")
    # Old watermarks do not record which traces ran or when. New allowances
    # start at rollout; never turn the historical corpus into inferred usage.
    op.execute(
        "CREATE INDEX idx_sessions_curated_at "
        "ON sessions(owner_user_id, curated_at) WHERE curated_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_sessions_curated_at")
    op.execute("ALTER TABLE sessions DROP COLUMN curated_at")
