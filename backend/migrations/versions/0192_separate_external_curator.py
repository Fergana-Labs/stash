"""A workspace curates its internal and external wikis separately.

A developer workspace can hold both wikis — its team's own Memory wiki and the
cross-org anonymized wiki its customers' agents read. One curator per user
could only ever write one of them: build_scheduled_turn picked the external
prompt whenever the developer platform was active, so the internal wiki simply
stopped being curated.

They are genuinely different jobs, not one job with a flag. The internal pass
names people and projects on purpose; the external pass must name no one, and
routes each org's material to that org's notepad. Two agent rows means two
schedules, two watermarks, and two run histories, so a failure in one is
visible as itself rather than as a gap in the other.

`curator_wiki` is which wiki a curator writes: 'internal' (the scope's Memory
wiki) or 'external' (the workspace's cross-org wiki). Existing curators are
internal — the external one is provisioned when a workspace activates the
developer platform.

Revision ID: 0192
Revises: 0191
"""

from alembic import op

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN curator_wiki VARCHAR(16)")
    op.execute("UPDATE agents SET curator_wiki = 'internal' WHERE is_curator")
    op.execute("DROP INDEX IF EXISTS one_curator_per_user")
    op.execute(
        "CREATE UNIQUE INDEX one_curator_per_user_per_wiki "
        "ON agents (user_id, curator_wiki) WHERE is_curator"
    )


def downgrade() -> None:
    op.execute("DELETE FROM agents WHERE is_curator AND curator_wiki = 'external'")
    op.execute("DROP INDEX IF EXISTS one_curator_per_user_per_wiki")
    op.execute("CREATE UNIQUE INDEX one_curator_per_user ON agents (user_id) WHERE is_curator")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS curator_wiki")
