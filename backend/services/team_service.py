"""Team surface: membership and usage analytics for a workspace.

Raw traces are never listed here — teammates see a transcript only via an
explicit per-person share. What the team shares automatically is the
*distilled* layer (the workspace curator's wiki + skills), whose inputs are
every member session not excluded from team memory.
"""

from uuid import UUID

from ..database import get_pool
from .permission_service import _workspace_member_condition_expr

# Rough tokens-from-characters divisor for usage analytics. An estimate is
# honest here (the column is labeled estimated); exact counts would need
# token counting at event ingest.
_CHARS_PER_TOKEN = 4


async def list_members(workspace_id: UUID) -> list[dict]:
    """Everyone in the workspace: on-domain verified users (derived) plus
    explicit off-domain adds. Mirrors `workspace_member_condition` exactly."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id, u.name, u.display_name, u.email "
        "FROM users u, workspaces w "
        "WHERE w.id = $1 AND "
        + _workspace_member_condition_expr("w", "u.id")
        + " ORDER BY lower(u.display_name)",
        workspace_id,
    )
    return [dict(row) for row in rows]


TEAM_SKILLS_FOLDER = "Team Skills"


async def get_or_create_team_skills_folder(scope_user_id: UUID) -> dict:
    """The workspace's skill library — a root folder OUTSIDE the Memory wiki.

    Experiment (2026-08-15): skills as a separate first-class store rather
    than a promoted wiki category, to compare how the two shapes feel. The
    curator writes short procedural pages here; the wiki keeps facts and
    decisions."""
    pool = get_pool()
    select = (
        "SELECT id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at "
        "FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL "
        "AND name = $2 LIMIT 1"
    )
    row = await pool.fetchrow(select, scope_user_id, TEAM_SKILLS_FOLDER)
    if row:
        return dict(row)
    row = await pool.fetchrow(
        "INSERT INTO folders (owner_user_id, name, created_by) VALUES ($1, $2, $1) "
        "ON CONFLICT DO NOTHING "
        "RETURNING id, owner_user_id, parent_folder_id, name, created_by, created_at, updated_at",
        scope_user_id,
        TEAM_SKILLS_FOLDER,
    )
    if row is None:  # lost a race — read the winner.
        row = await pool.fetchrow(select, scope_user_id, TEAM_SKILLS_FOLDER)
    return dict(row)


async def list_team_skills(scope_user_id: UUID) -> dict:
    """The skill library's pages, alphabetical. Creating the folder lazily
    means the section exists from a team's first day."""
    pool = get_pool()
    folder = await get_or_create_team_skills_folder(scope_user_id)
    pages = await pool.fetch(
        "SELECT id, name, updated_at FROM pages "
        "WHERE folder_id = $1 AND deleted_at IS NULL ORDER BY lower(name)",
        folder["id"],
    )
    return {"folder": folder, "skills": [dict(p) for p in pages]}


async def member_session_stats(workspace_id: UUID) -> list[dict]:
    """Per-member session counts and estimated token volume for org
    analytics. Metadata only — no titles, no content, no cwd: the audit
    surface must never become a way to read what the privacy default
    protects. Exclusion counts are deliberately NOT here: showing teammates
    who opts out how often creates social pressure against using the
    escape hatch, which would quietly break the consent design."""
    pool = get_pool()
    member = _workspace_member_condition_expr("w", "u.id")
    rows = await pool.fetch(
        f"""
        SELECT u.id, u.name, u.display_name,
               COUNT(DISTINCT s.id) FILTER (WHERE s.deleted_at IS NULL) AS sessions_total,
               COUNT(DISTINCT s.id) FILTER (
                 WHERE s.deleted_at IS NULL
                   AND s.started_at > now() - interval '7 days') AS sessions_7d,
               COUNT(DISTINCT s.id) FILTER (
                 WHERE s.deleted_at IS NULL
                   AND s.started_at > now() - interval '30 days') AS sessions_30d,
               MAX(s.started_at) FILTER (WHERE s.deleted_at IS NULL) AS last_session_at,
               (COALESCE(tok.chars_30d, 0) / {_CHARS_PER_TOKEN})::bigint AS est_tokens_30d
        FROM users u
        JOIN workspaces w ON w.id = $1
        LEFT JOIN sessions s ON s.owner_user_id = u.id
        LEFT JOIN LATERAL (
          SELECT SUM(length(he.content)) AS chars_30d
          FROM history_events he
          WHERE he.owner_user_id = u.id
            AND he.created_at > now() - interval '30 days'
        ) tok ON true
        WHERE {member}
        GROUP BY u.id, u.name, u.display_name, tok.chars_30d
        ORDER BY sessions_30d DESC, lower(u.display_name)
        """,
        workspace_id,
    )
    return [dict(row) for row in rows]
