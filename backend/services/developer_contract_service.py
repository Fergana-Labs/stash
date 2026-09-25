"""Explicit rollout exception for Heavi's deployed wiki integration."""

from uuid import UUID

from ..database import get_pool


async def uses_wiki(owner_user_id: UUID, *, conn=None) -> bool:
    db = get_pool() if conn is None else conn
    return await db.fetchval(
        "SELECT EXISTS (SELECT 1 FROM workspaces WHERE scope_user_id=$1 AND legacy_wiki_enabled)",
        owner_user_id,
    )


def wiki_fields(value):
    """Keep Heavi's existing console fields alongside the current app's fields."""
    names = {
        "external_skill_folder_id": "external_wiki_folder_id",
        "end_user_skills_folder_id": "end_user_wikis_folder_id",
        "skill_folder_id": "wiki_folder_id",
        "share_skill": "share_wiki",
        "skill_pages": "wiki_pages",
        "skill_files": "wiki_files",
        "skill_page_count": "wiki_page_count",
    }
    if isinstance(value, list):
        return [wiki_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: wiki_fields(item) for key, item in value.items()}
    for key, alias in names.items():
        if key in result:
            result[alias] = result[key]
    return result


async def response(owner_user_id: UUID, value):
    return wiki_fields(value) if await uses_wiki(owner_user_id) else value
