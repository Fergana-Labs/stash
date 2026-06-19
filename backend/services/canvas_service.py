"""Canvas service: agent-generated generative-UI artifacts, persisted per workspace.

A canvas is the "UI" half of the agent-as-coworker model — the panel the agent
renders beside the chat. It is a title plus an ordered list of blocks (pre-built
components or raw HTML). Canvases are stored so a generated view can be reopened
and refined later, which is how an ad-hoc view "solidifies" over time.
"""

from uuid import UUID

from ..database import get_pool

_FIELDS = (
    "id, workspace_id, session_id, title, blocks, "
    "created_by, updated_by, created_at, updated_at"
)


async def create_canvas(
    workspace_id: UUID,
    title: str,
    blocks: list[dict],
    created_by: UUID,
    session_id: str | None = None,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO canvases (workspace_id, session_id, title, blocks, created_by, updated_by) "
        f"VALUES ($1, $2, $3, $4, $5, $5) RETURNING {_FIELDS}",
        workspace_id,
        session_id,
        title,
        blocks,
        created_by,
    )
    return dict(row)


async def get_canvas(canvas_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(f"SELECT {_FIELDS} FROM canvases WHERE id = $1", canvas_id)
    return dict(row) if row else None


async def update_canvas(
    canvas_id: UUID,
    updated_by: UUID,
    title: str | None = None,
    blocks: list[dict] | None = None,
) -> dict | None:
    pool = get_pool()
    sets = ["updated_at = now()", "updated_by = $1"]
    args: list = [updated_by]
    idx = 2
    if title is not None:
        sets.append(f"title = ${idx}")
        args.append(title)
        idx += 1
    if blocks is not None:
        sets.append(f"blocks = ${idx}")
        args.append(blocks)
        idx += 1
    args.append(canvas_id)
    row = await pool.fetchrow(
        f"UPDATE canvases SET {', '.join(sets)} WHERE id = ${idx} RETURNING {_FIELDS}",
        *args,
    )
    return dict(row) if row else None


async def list_canvases(
    workspace_id: UUID, session_id: str | None = None, limit: int = 50
) -> list[dict]:
    pool = get_pool()
    if session_id is not None:
        rows = await pool.fetch(
            f"SELECT {_FIELDS} FROM canvases WHERE workspace_id = $1 AND session_id = $2 "
            "ORDER BY updated_at DESC LIMIT $3",
            workspace_id,
            session_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            f"SELECT {_FIELDS} FROM canvases WHERE workspace_id = $1 "
            "ORDER BY updated_at DESC LIMIT $2",
            workspace_id,
            limit,
        )
    return [dict(r) for r in rows]


async def delete_canvas(canvas_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM canvases WHERE id = $1", canvas_id)
    return result == "DELETE 1"
