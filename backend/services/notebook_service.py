"""Notebook service: markdown file/folder CRUD with Yjs collaborative editing."""

from uuid import UUID

from ..database import get_pool


# --- Folders ---


async def create_folder(workspace_id: UUID, name: str, created_by: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebook_folders (workspace_id, name, created_by) "
        "VALUES ($1, $2, $3) "
        "RETURNING id, workspace_id, name, created_by, created_at, updated_at",
        workspace_id, name, created_by,
    )
    return dict(row)


async def rename_folder(folder_id: UUID, workspace_id: UUID, name: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE notebook_folders SET name = $1, updated_at = now() "
        "WHERE id = $2 AND workspace_id = $3 "
        "RETURNING id, workspace_id, name, created_by, created_at, updated_at",
        name, folder_id, workspace_id,
    )
    return dict(row) if row else None


async def delete_folder(folder_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebook_folders WHERE id = $1 AND workspace_id = $2",
        folder_id, workspace_id,
    )
    return result == "DELETE 1"


# --- Notebooks ---


async def create_notebook(
    workspace_id: UUID, name: str, created_by: UUID,
    folder_id: UUID | None = None, content: str = "",
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebooks (workspace_id, folder_id, name, content_markdown, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $5) "
        "RETURNING id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at",
        workspace_id, folder_id, name, content, created_by,
    )
    return dict(row)


async def get_notebook(notebook_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at "
        "FROM notebooks WHERE id = $1 AND workspace_id = $2",
        notebook_id, workspace_id,
    )
    return dict(row) if row else None


async def update_notebook(
    notebook_id: UUID, workspace_id: UUID, updated_by: UUID,
    name: str | None = None, folder_id: UUID | None = None,
    content: str | None = None, yjs_state: bytes | None = None,
    move_to_root: bool = False,
) -> dict | None:
    pool = get_pool()
    sets = ["updated_at = now()", "updated_by = $1"]
    args: list = [updated_by]
    idx = 2

    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if move_to_root:
        sets.append("folder_id = NULL")
    elif folder_id is not None:
        sets.append(f"folder_id = ${idx}")
        args.append(folder_id)
        idx += 1
    if content is not None:
        sets.append(f"content_markdown = ${idx}")
        args.append(content)
        idx += 1
    if yjs_state is not None:
        sets.append(f"yjs_state = ${idx}")
        args.append(yjs_state)
        idx += 1

    args.append(notebook_id)
    args.append(workspace_id)
    row = await pool.fetchrow(
        f"UPDATE notebooks SET {', '.join(sets)} "
        f"WHERE id = ${idx} AND workspace_id = ${idx + 1} "
        "RETURNING id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    return dict(row) if row else None


async def delete_notebook(notebook_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebooks WHERE id = $1 AND workspace_id = $2",
        notebook_id, workspace_id,
    )
    return result == "DELETE 1"


async def list_notebook_tree(workspace_id: UUID) -> dict:
    """List all notebooks and folders in a workspace as a tree."""
    pool = get_pool()
    folders = await pool.fetch(
        "SELECT id, workspace_id, name, created_by, created_at, updated_at "
        "FROM notebook_folders WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )
    files = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, created_at, updated_at "
        "FROM notebooks WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )

    folder_map: dict[UUID, dict] = {}
    for f in folders:
        fd = dict(f)
        fd["files"] = []
        folder_map[fd["id"]] = fd

    root_files = []
    for fi in files:
        fid = dict(fi)
        if fid["folder_id"] and fid["folder_id"] in folder_map:
            folder_map[fid["folder_id"]]["files"].append(fid)
        else:
            root_files.append(fid)

    return {"folders": list(folder_map.values()), "root_files": root_files}


# --- Yjs ---


async def save_yjs_state(
    notebook_id: UUID, workspace_id: UUID,
    yjs_state: bytes, content_markdown: str | None = None,
) -> None:
    pool = get_pool()
    if content_markdown is not None:
        await pool.execute(
            "UPDATE notebooks SET yjs_state = $1, content_markdown = $2, updated_at = now() "
            "WHERE id = $3 AND workspace_id = $4",
            yjs_state, content_markdown, notebook_id, workspace_id,
        )
    else:
        await pool.execute(
            "UPDATE notebooks SET yjs_state = $1, updated_at = now() "
            "WHERE id = $2 AND workspace_id = $3",
            yjs_state, notebook_id, workspace_id,
        )


async def get_yjs_state(notebook_id: UUID, workspace_id: UUID) -> bytes | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT yjs_state FROM notebooks WHERE id = $1 AND workspace_id = $2",
        notebook_id, workspace_id,
    )
    return row["yjs_state"] if row else None
