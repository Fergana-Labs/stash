"""Remove the notebook layer; folders nest under workspace.

Collapses Workspace -> Notebook -> (Folder | Page) into Workspace -> (Folder | Page).
Each existing notebook becomes a top-level folder named after the notebook;
folders that lived inside a notebook gain parent_folder_id = that new folder.
Pages at notebook root move into the new folder; pages already in a subfolder
keep their folder_id and gain workspace_id directly.

Visibility for folders/pages continues to live in object_permissions; rows
keyed by object_type='notebook' are repointed to object_type='folder' against
the freshly-created top-level folder. Same remap for object_shares and
view_items (which also gains 'page' as a valid object_type).

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


_NEW_OBJECT_TYPES = (
    "('workspace', 'chat', 'folder', 'page', 'history', 'deck', 'table', 'file', 'view')"
)


def upgrade() -> None:
    # 1. New columns on the soon-to-be-renamed tables. notebook_id is also
    # dropped from NOT NULL so we can insert the new top-level folders, which
    # don't belong to any notebook.
    op.execute(
        "ALTER TABLE notebook_folders "
        "ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE, "
        "ADD COLUMN parent_folder_id UUID REFERENCES notebook_folders(id) ON DELETE CASCADE, "
        "ALTER COLUMN notebook_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE notebook_pages "
        "ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE"
    )

    # 2. Materialize one new top-level folder per notebook and capture the
    # mapping. The temp table lives only for this migration.
    op.execute(
        "CREATE TEMP TABLE notebook_to_folder_map ("
        "notebook_id UUID PRIMARY KEY, folder_id UUID NOT NULL"
        ") ON COMMIT DROP"
    )
    # Single CTE generates the new folder UUIDs alongside the source notebook
    # id so the insert + map population both see the same rows.
    #
    # Notebooks never had a (workspace_id, name) unique constraint, but the
    # new folders table will (idx_folders_unique_at_root). Disambiguate
    # duplicates here by appending a numeric suffix to every collision after
    # the first, ordered by created_at. The first notebook keeps its name.
    op.execute(
        "WITH new_folders AS ("
        "  SELECT"
        "    n.id AS notebook_id,"
        "    gen_random_uuid() AS folder_id,"
        "    CASE"
        "      WHEN ROW_NUMBER() OVER ("
        "        PARTITION BY n.workspace_id, n.name ORDER BY n.created_at, n.id"
        "      ) = 1 THEN n.name"
        "      ELSE n.name || ' ('"
        "        || ROW_NUMBER() OVER ("
        "          PARTITION BY n.workspace_id, n.name ORDER BY n.created_at, n.id"
        "        )::text || ')'"
        "    END AS name,"
        "    n.workspace_id, n.created_by, n.created_at, n.updated_at "
        "  FROM notebooks n"
        "), "
        "ins AS ("
        "  INSERT INTO notebook_folders "
        "    (id, name, workspace_id, parent_folder_id, created_by, created_at, updated_at) "
        "  SELECT folder_id, name, workspace_id, NULL, created_by, created_at, updated_at "
        "  FROM new_folders "
        "  RETURNING id"
        ") "
        "INSERT INTO notebook_to_folder_map (notebook_id, folder_id) "
        "SELECT notebook_id, folder_id FROM new_folders"
    )

    # 3. Backfill the original folder rows: workspace_id from their notebook,
    # parent_folder_id pointing at the new top-level folder. Skip the rows we
    # just inserted (those have notebook_id IS NULL after the next step would
    # be ambiguous; instead filter by absence in the map).
    op.execute(
        "UPDATE notebook_folders f "
        "SET workspace_id = n.workspace_id, parent_folder_id = m.folder_id "
        "FROM notebooks n JOIN notebook_to_folder_map m ON m.notebook_id = n.id "
        "WHERE f.notebook_id = n.id "
        "  AND NOT EXISTS (SELECT 1 FROM notebook_to_folder_map m2 WHERE m2.folder_id = f.id)"
    )

    # 4. Backfill pages: workspace_id from the notebook; pages at notebook root
    # (folder_id IS NULL) get reparented into the new top-level folder.
    op.execute(
        "UPDATE notebook_pages p "
        "SET workspace_id = n.workspace_id, "
        "    folder_id = COALESCE(p.folder_id, m.folder_id) "
        "FROM notebooks n JOIN notebook_to_folder_map m ON m.notebook_id = n.id "
        "WHERE p.notebook_id = n.id"
    )

    # 5. Remap visibility/share/view_items rows from 'notebook' to 'folder'.
    # The existing CHECK constraints on all three tables disallow 'folder', so
    # we drop the constraints first, run the UPDATEs, then recreate the CHECKs
    # with the new vocabulary.
    op.execute(
        "ALTER TABLE object_permissions DROP CONSTRAINT IF EXISTS object_permissions_object_type_check"
    )
    op.execute(
        "ALTER TABLE object_shares DROP CONSTRAINT IF EXISTS object_shares_object_type_check"
    )
    op.execute("ALTER TABLE view_items DROP CONSTRAINT IF EXISTS view_items_object_type_check")

    op.execute(
        "UPDATE object_permissions op "
        "SET object_type = 'folder', object_id = m.folder_id "
        "FROM notebook_to_folder_map m "
        "WHERE op.object_type = 'notebook' AND op.object_id = m.notebook_id"
    )
    op.execute(
        "UPDATE object_shares os "
        "SET object_type = 'folder', object_id = m.folder_id "
        "FROM notebook_to_folder_map m "
        "WHERE os.object_type = 'notebook' AND os.object_id = m.notebook_id"
    )
    op.execute(
        "UPDATE view_items vi "
        "SET object_type = 'folder', object_id = m.folder_id "
        "FROM notebook_to_folder_map m "
        "WHERE vi.object_type = 'notebook' AND vi.object_id = m.notebook_id"
    )

    op.execute(
        f"ALTER TABLE object_permissions ADD CONSTRAINT object_permissions_object_type_check "
        f"CHECK (object_type IN {_NEW_OBJECT_TYPES})"
    )
    op.execute(
        f"ALTER TABLE object_shares ADD CONSTRAINT object_shares_object_type_check "
        f"CHECK (object_type IN {_NEW_OBJECT_TYPES})"
    )
    op.execute(
        "ALTER TABLE view_items ADD CONSTRAINT view_items_object_type_check "
        "CHECK (object_type IN ('folder', 'page', 'table', 'file', 'history'))"
    )

    # 6. Tighten the new columns now that backfill is complete.
    op.execute("ALTER TABLE notebook_folders ALTER COLUMN workspace_id SET NOT NULL")
    op.execute("ALTER TABLE notebook_pages ALTER COLUMN workspace_id SET NOT NULL")

    # 7. Drop notebook-scoped indexes/uniques before we lose notebook_id.
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_unique_in_folder")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_unique_at_root")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_root_unique")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_folder_unique")
    op.execute("DROP INDEX IF EXISTS idx_personal_notebook_unique")
    op.execute("DROP INDEX IF EXISTS idx_notebooks_personal")
    op.execute("DROP INDEX IF EXISTS idx_notebooks_workspace")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_notebook")
    op.execute("DROP INDEX IF EXISTS idx_notebook_folders_notebook")

    # 8. Drop notebook_id columns and the notebooks table itself.
    op.execute("ALTER TABLE notebook_folders DROP COLUMN notebook_id")
    op.execute("ALTER TABLE notebook_pages DROP COLUMN notebook_id")
    op.execute("DROP TABLE notebooks CASCADE")

    # 9. Rename tables to drop the notebook_ prefix.
    op.execute("ALTER TABLE notebook_folders RENAME TO folders")
    op.execute("ALTER TABLE notebook_pages RENAME TO pages")
    op.execute("ALTER INDEX IF EXISTS idx_notebook_pages_folder RENAME TO idx_pages_folder")
    op.execute("ALTER INDEX IF EXISTS idx_notebook_pages_fts RENAME TO idx_pages_fts")
    op.execute("ALTER INDEX IF EXISTS idx_notebook_pages_embedding RENAME TO idx_pages_embedding")
    op.execute(
        "ALTER INDEX IF EXISTS idx_notebook_pages_embed_stale RENAME TO idx_pages_embed_stale"
    )

    # 10. Workspace-scoped indexes + uniqueness on the new tables. Pages and
    # folders both partition the namespace by (workspace, parent, name).
    op.execute("CREATE INDEX idx_folders_workspace ON folders(workspace_id)")
    op.execute(
        "CREATE INDEX idx_folders_parent ON folders(parent_folder_id) "
        "WHERE parent_folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_folders_unique_in_parent "
        "ON folders(workspace_id, parent_folder_id, name) "
        "WHERE parent_folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_folders_unique_at_root "
        "ON folders(workspace_id, name) "
        "WHERE parent_folder_id IS NULL"
    )
    op.execute("CREATE INDEX idx_pages_workspace ON pages(workspace_id)")
    op.execute(
        "CREATE UNIQUE INDEX idx_pages_unique_in_folder "
        "ON pages(workspace_id, folder_id, name) "
        "WHERE folder_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_pages_unique_at_root "
        "ON pages(workspace_id, name) "
        "WHERE folder_id IS NULL"
    )
    # Cycle prevention. App-level walk handles deeper cycles on PATCH; the
    # CHECK guards the trivial self-reference case at the storage layer.
    op.execute(
        "ALTER TABLE folders ADD CONSTRAINT folders_no_self_parent CHECK (id <> parent_folder_id)"
    )


def downgrade() -> None:
    # The rename + data flattening is not reversible without snapshotting the
    # original notebook->page mapping, which we don't keep. Forward-only.
    raise NotImplementedError("0026 is forward-only")
