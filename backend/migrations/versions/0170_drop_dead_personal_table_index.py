"""Drop idx_personal_table_unique — it guards a state nothing can reach.

The index was created in 0001 as UNIQUE(created_by, name) WHERE workspace_id
IS NULL: uniqueness for "personal" tables, the ones that lived outside a
workspace. Removing workspaces (#667) made every table user-scoped and
rewrote the predicate to `owner_user_id IS NULL`, but nothing rewrote what it
was for.

Today every create_table caller derives owner_user_id from the request scope
(`get_scope`, a non-optional UUID) or from agent_runtime._current_scope(),
which raises rather than return None. So no writer can produce a row matching
the predicate, and the index constrains nothing.

Leaving it is worse than neutral: it reads as partial uniqueness on `tables`
and invites the conclusion that name collisions are guarded somewhere. They
are not, and deliberately so — duplicate table names are legal, the same way
duplicate file names are. The one place that genuinely needed get-or-create
uniqueness is mini programs, which has its own index (0168).

Dropping an index touches no rows. Any historical owner_user_id IS NULL
tables stay exactly as they are and stay readable.
"""

from alembic import op

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_personal_table_unique")


def downgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_table_unique "
        "ON tables(created_by, name) WHERE owner_user_id IS NULL"
    )
