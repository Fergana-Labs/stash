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


# --- Aggregate Notebooks ---


async def list_all_user_notebooks(user_id: UUID) -> list[dict]:
    """All notebooks: from workspaces user is member of + personal."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT n.id, n.workspace_id, n.folder_id, n.name, "
        "n.created_by, n.updated_by, n.created_at, n.updated_at, "
        "w.name AS workspace_name "
        "FROM notebooks n "
        "LEFT JOIN workspaces w ON w.id = n.workspace_id "
        "WHERE n.workspace_id IN ("
        "  SELECT workspace_id FROM workspace_members WHERE user_id = $1"
        ") OR (n.workspace_id IS NULL AND n.created_by = $1) "
        "ORDER BY n.updated_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


# --- Personal Notebooks ---


async def create_personal_notebook(
    name: str, created_by: UUID,
    folder_id: UUID | None = None, content: str = "",
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebooks (workspace_id, folder_id, name, content_markdown, created_by, updated_by) "
        "VALUES (NULL, $1, $2, $3, $4, $4) "
        "RETURNING id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at",
        folder_id, name, content, created_by,
    )
    return dict(row)


async def get_personal_notebook(notebook_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at "
        "FROM notebooks WHERE id = $1 AND workspace_id IS NULL AND created_by = $2",
        notebook_id, user_id,
    )
    return dict(row) if row else None


async def update_personal_notebook(
    notebook_id: UUID, user_id: UUID,
    name: str | None = None, folder_id: UUID | None = None,
    content: str | None = None, move_to_root: bool = False,
) -> dict | None:
    pool = get_pool()
    sets = ["updated_at = now()", "updated_by = $1"]
    args: list = [user_id]
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

    args.append(notebook_id)
    args.append(user_id)
    row = await pool.fetchrow(
        f"UPDATE notebooks SET {', '.join(sets)} "
        f"WHERE id = ${idx} AND workspace_id IS NULL AND created_by = ${idx + 1} "
        "RETURNING id, workspace_id, folder_id, name, content_markdown, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    return dict(row) if row else None


async def delete_personal_notebook(notebook_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebooks WHERE id = $1 AND workspace_id IS NULL AND created_by = $2",
        notebook_id, user_id,
    )
    return result == "DELETE 1"


async def list_personal_notebook_tree(user_id: UUID) -> dict:
    """List all personal notebooks and folders as a tree."""
    pool = get_pool()
    folders = await pool.fetch(
        "SELECT id, workspace_id, name, created_by, created_at, updated_at "
        "FROM notebook_folders WHERE workspace_id IS NULL AND created_by = $1 ORDER BY name",
        user_id,
    )
    files = await pool.fetch(
        "SELECT id, workspace_id, folder_id, name, created_at, updated_at "
        "FROM notebooks WHERE workspace_id IS NULL AND created_by = $1 ORDER BY name",
        user_id,
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


async def create_personal_folder(name: str, created_by: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO notebook_folders (workspace_id, name, created_by) "
        "VALUES (NULL, $1, $2) "
        "RETURNING id, workspace_id, name, created_by, created_at, updated_at",
        name, created_by,
    )
    return dict(row)


async def rename_personal_folder(folder_id: UUID, user_id: UUID, name: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE notebook_folders SET name = $1, updated_at = now() "
        "WHERE id = $2 AND workspace_id IS NULL AND created_by = $3 "
        "RETURNING id, workspace_id, name, created_by, created_at, updated_at",
        name, folder_id, user_id,
    )
    return dict(row) if row else None


async def delete_personal_folder(folder_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM notebook_folders WHERE id = $1 AND workspace_id IS NULL AND created_by = $2",
        folder_id, user_id,
    )
    return result == "DELETE 1"


# --- Yjs ---


async def save_yjs_state(
    notebook_id: UUID, workspace_id: UUID | str | None,
    yjs_state: bytes, content_markdown: str | None = None,
) -> None:
    pool = get_pool()
    ws_cond = "workspace_id IS NULL" if workspace_id is None else "workspace_id = ${}".format(
        4 if content_markdown is not None else 3
    )
    if content_markdown is not None:
        args = [yjs_state, content_markdown, notebook_id]
        if workspace_id is not None:
            args.append(workspace_id)
        await pool.execute(
            f"UPDATE notebooks SET yjs_state = $1, content_markdown = $2, updated_at = now() "
            f"WHERE id = $3 AND {ws_cond}",
            *args,
        )
    else:
        args = [yjs_state, notebook_id]
        if workspace_id is not None:
            args.append(workspace_id)
        await pool.execute(
            f"UPDATE notebooks SET yjs_state = $1, updated_at = now() "
            f"WHERE id = $2 AND {ws_cond}",
            *args,
        )


async def get_yjs_state(notebook_id: UUID, workspace_id: UUID | str | None) -> bytes | None:
    pool = get_pool()
    if workspace_id is None:
        row = await pool.fetchrow(
            "SELECT yjs_state FROM notebooks WHERE id = $1 AND workspace_id IS NULL",
            notebook_id,
        )
    else:
        row = await pool.fetchrow(
            "SELECT yjs_state FROM notebooks WHERE id = $1 AND workspace_id = $2",
            notebook_id, workspace_id,
        )
    return row["yjs_state"] if row else None
