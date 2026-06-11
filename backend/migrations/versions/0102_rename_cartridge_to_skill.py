"""Rename the bundle concept Cartridge → Skill.

The product/brand "Stash" and the CLI stay; only the *bundle* entity is
renamed. Unlike 0081 (which left old constraint/index names as "cosmetic"),
this migration also renames the accumulated `views_*` / `stash_*` constraint
and index fossils so the catalog finally matches the code.

Also fixes a latent 0081 bug: three partial indexes on `pages` still
predicated on the pre-0081 metadata key `shared_in_stash_id`, so since 0081
the two UNIQUE ones applied uniqueness to bundle-shared snapshot pages they
were meant to exclude, and the planner could never use the third. They are
recreated against the new `shared_in_skill_id` key.

Revision ID: 0102
Revises: 0101
"""

from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

# (current name, new name) — verified against a head-of-history catalog.
_CONSTRAINT_RENAMES = {
    "skills": [
        ("views_pkey", "skills_pkey"),
        ("views_slug_key", "skills_slug_key"),
        ("views_workspace_id_fkey", "skills_workspace_id_fkey"),
        ("views_owner_id_fkey", "skills_owner_id_fkey"),
        ("stashes_forked_from_stash_id_fkey", "skills_forked_from_skill_id_fkey"),
        ("stashes_workspace_permission_check", "skills_workspace_permission_check"),
        ("stashes_public_permission_check", "skills_public_permission_check"),
    ],
    "skill_items": [
        ("view_items_pkey", "skill_items_pkey"),
        ("view_items_view_id_fkey", "skill_items_skill_id_fkey"),
        ("stash_items_object_type_check", "skill_items_object_type_check"),
    ],
    "skill_members": [
        ("stash_members_pkey", "skill_members_pkey"),
        ("stash_members_stash_id_fkey", "skill_members_skill_id_fkey"),
        ("stash_members_user_id_fkey", "skill_members_user_id_fkey"),
        ("stash_members_granted_by_fkey", "skill_members_granted_by_fkey"),
        ("stash_members_permission_check", "skill_members_permission_check"),
    ],
    "skill_invites": [
        ("stash_invites_pkey", "skill_invites_pkey"),
        ("stash_invites_stash_id_fkey", "skill_invites_skill_id_fkey"),
        ("stash_invites_recipient_user_id_fkey", "skill_invites_recipient_user_id_fkey"),
        ("stash_invites_invited_by_user_id_fkey", "skill_invites_invited_by_user_id_fkey"),
        ("stash_invites_target_workspace_id_fkey", "skill_invites_target_workspace_id_fkey"),
        ("stash_invites_permission_check", "skill_invites_permission_check"),
        ("stash_invites_status_check", "skill_invites_status_check"),
        (
            "stash_invites_stash_id_recipient_user_id_key",
            "skill_invites_skill_id_recipient_user_id_key",
        ),
    ],
}

# Pure index renames (PK/unique-constraint indexes rename with their
# constraint above).
_INDEX_RENAMES = [
    ("idx_stashes_workspace", "idx_skills_workspace"),
    ("idx_stashes_discover", "idx_skills_discover"),
    ("idx_stashes_one_fork_per_workspace", "idx_skills_one_fork_per_workspace"),
    ("idx_stash_items_position", "idx_skill_items_position"),
    ("idx_stash_members_user", "idx_skill_members_user"),
    ("idx_stash_invites_recipient_status", "idx_skill_invites_recipient_status"),
]


def _rename_pages_partial_indexes(metadata_key: str) -> None:
    """Recreate the three pages partial indexes against the given metadata key."""
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_in_folder")
    op.execute(f"""
        CREATE UNIQUE INDEX idx_pages_unique_in_folder
        ON pages (workspace_id, folder_id, name)
        WHERE folder_id IS NOT NULL
          AND COALESCE(metadata->>'{metadata_key}', '') = ''
        """)
    op.execute("DROP INDEX IF EXISTS idx_pages_unique_at_root")
    op.execute(f"""
        CREATE UNIQUE INDEX idx_pages_unique_at_root
        ON pages (workspace_id, name)
        WHERE folder_id IS NULL
          AND COALESCE(metadata->>'{metadata_key}', '') = ''
        """)
    op.execute("DROP INDEX IF EXISTS idx_pages_workspace_active_folder_name")
    op.execute(f"""
        CREATE INDEX idx_pages_workspace_active_folder_name
        ON pages (workspace_id, folder_id, name)
        WHERE deleted_at IS NULL
          AND COALESCE(metadata->>'{metadata_key}', '') = ''
        """)


def upgrade() -> None:
    op.execute("ALTER TABLE cartridges RENAME TO skills")
    op.execute("ALTER TABLE cartridge_items RENAME TO skill_items")
    op.execute("ALTER TABLE cartridge_members RENAME TO skill_members")
    op.execute("ALTER TABLE cartridge_invites RENAME TO skill_invites")

    op.execute("ALTER TABLE skills RENAME COLUMN forked_from_cartridge_id TO forked_from_skill_id")
    op.execute("ALTER TABLE skill_items RENAME COLUMN cartridge_id TO skill_id")
    op.execute("ALTER TABLE skill_members RENAME COLUMN cartridge_id TO skill_id")
    op.execute("ALTER TABLE skill_invites RENAME COLUMN cartridge_id TO skill_id")

    for table, renames in _CONSTRAINT_RENAMES.items():
        for old, new in renames:
            op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")

    # The privacy marker stamped on pages/files moves with the rename.
    for table in ("pages", "files"):
        op.execute(f"""
            UPDATE {table}
            SET metadata = (metadata - 'shared_in_cartridge_id')
                           || jsonb_build_object('shared_in_skill_id', metadata->'shared_in_cartridge_id')
            WHERE metadata ? 'shared_in_cartridge_id'
            """)

    _rename_pages_partial_indexes("shared_in_skill_id")

    # Per-user UI state stores the kind strings the frontend sends.
    op.execute("UPDATE user_pins SET kind = 'skills' WHERE kind = 'cartridges'")
    op.execute("UPDATE user_recents SET kind = 'skill' WHERE kind = 'stash'")


def downgrade() -> None:
    op.execute("UPDATE user_recents SET kind = 'stash' WHERE kind = 'skill'")
    op.execute("UPDATE user_pins SET kind = 'cartridges' WHERE kind = 'skills'")

    _rename_pages_partial_indexes("shared_in_cartridge_id")

    for table in ("pages", "files"):
        op.execute(f"""
            UPDATE {table}
            SET metadata = (metadata - 'shared_in_skill_id')
                           || jsonb_build_object('shared_in_cartridge_id', metadata->'shared_in_skill_id')
            WHERE metadata ? 'shared_in_skill_id'
            """)

    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
    for table, renames in _CONSTRAINT_RENAMES.items():
        for old, new in renames:
            op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}")

    op.execute("ALTER TABLE skill_invites RENAME COLUMN skill_id TO cartridge_id")
    op.execute("ALTER TABLE skill_members RENAME COLUMN skill_id TO cartridge_id")
    op.execute("ALTER TABLE skill_items RENAME COLUMN skill_id TO cartridge_id")
    op.execute("ALTER TABLE skills RENAME COLUMN forked_from_skill_id TO forked_from_cartridge_id")
    op.execute("ALTER TABLE skill_invites RENAME TO cartridge_invites")
    op.execute("ALTER TABLE skill_members RENAME TO cartridge_members")
    op.execute("ALTER TABLE skill_items RENAME TO cartridge_items")
    op.execute("ALTER TABLE skills RENAME TO cartridges")
