"""Which sessions a page was built from — and what that unlocks.

Provenance turns two prompt-level hopes into mechanisms:
- Excluding a session from team memory flags every page derived from it
  (`needs_recuration`), so the curator's next run rebuilds them without the
  excluded material. Opt-out reaches the past, not just the future.
- A workspace's Team Skills page must cite sessions from >=2 distinct
  authors. The bar is checked at write time and fails loud — never trusted
  to the curator's good behavior.
"""

from uuid import UUID

from ..database import get_pool
from .team_service import TEAM_SKILLS_FOLDER


class SkillsBarNotMet(Exception):
    """A Team Skills write without >=2 distinct authors' sessions behind it."""


async def enforce_team_skills_bar(
    folder_id: UUID | None, sources: list[tuple[UUID, str]] | None
) -> None:
    """Writes into a workspace's Team Skills folder must cite sessions from
    at least two distinct authors. Other folders (and personal scopes, which
    have no workspace row) are unaffected."""
    if folder_id is None:
        return
    pool = get_pool()
    is_team_skills = await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM folders f "
        "JOIN workspaces w ON w.scope_user_id = f.owner_user_id "
        "WHERE f.id = $1 AND f.parent_folder_id IS NULL AND f.name = $2)",
        folder_id,
        TEAM_SKILLS_FOLDER,
    )
    if not is_team_skills:
        return
    distinct_authors = {owner for owner, _ in (sources or [])}
    if len(distinct_authors) < 2:
        raise SkillsBarNotMet(
            "A team skill needs supporting sessions from at least two people "
            "(pass source_sessions with >=2 distinct authors)."
        )


async def set_sources(page_id: UUID, sources: list[tuple[UUID, str]]) -> None:
    """Replace the page's recorded sources and clear its recuration flag —
    a write that states fresh sources IS the rebuild."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM page_sources WHERE page_id = $1", page_id)
            await conn.executemany(
                "INSERT INTO page_sources (page_id, session_owner_user_id, session_id) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                [(page_id, owner, session_id) for owner, session_id in sources],
            )
            await conn.execute("UPDATE pages SET needs_recuration = false WHERE id = $1", page_id)


async def flag_pages_for_session(session_owner_user_id: UUID, session_id: str) -> int:
    """Mark every page built from this session for recuration. Returns the
    count so the consent surface can show the flip's real consequences."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE pages SET needs_recuration = true "
        "WHERE deleted_at IS NULL AND id IN "
        "(SELECT page_id FROM page_sources "
        " WHERE session_owner_user_id = $1 AND session_id = $2)",
        session_owner_user_id,
        session_id,
    )
    return int(result.split(" ")[-1])
