"""Hide Claude hook uploads that duplicated Stash's internal curator logs."""

import uuid

from alembic import op
from sqlalchemy import text

revision = "0226"
down_revision = "0225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    runs = (
        bind.execute(
            text(
                "SELECT DISTINCT owner_user_id,session_id FROM history_events "
                "WHERE session_id LIKE 'agent-curate-%' AND owner_user_id IS NOT NULL"
            )
        )
        .mappings()
        .all()
    )
    for run in runs:
        native_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"stash-agent:{run['session_id']}"))
        bind.execute(
            text(
                "UPDATE sessions SET deleted_at=now() "
                "WHERE owner_user_id=:owner AND session_id=:native AND deleted_at IS NULL"
            ),
            {"owner": run["owner_user_id"], "native": native_id},
        )


def downgrade() -> None:
    pass
