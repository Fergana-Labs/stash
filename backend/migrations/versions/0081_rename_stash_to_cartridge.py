"""Rename the bundle concept Stash → Cartridge.

The product/brand "Stash" and the CLI stay; only the *bundle* entity is renamed.
Tables, the per-bundle FK columns, and the page/file metadata marker are renamed.
Postgres carries FK references across a table rename automatically; we leave the
old constraint/index names (cosmetic) to keep this migration tight.

`stash_items` is renamed to `cartridge_items` here for a uniform rename; commit C3
then replaces it with the generic `shares` table.

Revision ID: 0081
Revises: 0080
"""

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stashes RENAME TO cartridges")
    op.execute("ALTER TABLE stash_items RENAME TO cartridge_items")
    op.execute("ALTER TABLE stash_members RENAME TO cartridge_members")
    op.execute("ALTER TABLE stash_invites RENAME TO cartridge_invites")

    op.execute(
        "ALTER TABLE cartridges RENAME COLUMN forked_from_stash_id TO forked_from_cartridge_id"
    )
    op.execute("ALTER TABLE cartridge_items RENAME COLUMN stash_id TO cartridge_id")
    op.execute("ALTER TABLE cartridge_members RENAME COLUMN stash_id TO cartridge_id")
    op.execute("ALTER TABLE cartridge_invites RENAME COLUMN stash_id TO cartridge_id")

    # The privacy marker stamped on pages/files moves with the rename.
    for table in ("pages", "files"):
        op.execute(f"""
            UPDATE {table}
            SET metadata = (metadata - 'shared_in_stash_id')
                           || jsonb_build_object('shared_in_cartridge_id', metadata->'shared_in_stash_id')
            WHERE metadata ? 'shared_in_stash_id'
            """)


def downgrade() -> None:
    op.execute("ALTER TABLE cartridge_invites RENAME COLUMN cartridge_id TO stash_id")
    op.execute("ALTER TABLE cartridge_members RENAME COLUMN cartridge_id TO stash_id")
    op.execute("ALTER TABLE cartridge_items RENAME COLUMN cartridge_id TO stash_id")
    op.execute(
        "ALTER TABLE cartridges RENAME COLUMN forked_from_cartridge_id TO forked_from_stash_id"
    )
    op.execute("ALTER TABLE cartridge_invites RENAME TO stash_invites")
    op.execute("ALTER TABLE cartridge_members RENAME TO stash_members")
    op.execute("ALTER TABLE cartridge_items RENAME TO stash_items")
    op.execute("ALTER TABLE cartridges RENAME TO stashes")
    for table in ("pages", "files"):
        op.execute(f"""
            UPDATE {table}
            SET metadata = (metadata - 'shared_in_cartridge_id')
                           || jsonb_build_object('shared_in_stash_id', metadata->'shared_in_cartridge_id')
            WHERE metadata ? 'shared_in_cartridge_id'
            """)
