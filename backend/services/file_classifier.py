"""Where a dropped file belongs, chosen from the folders that already exist.

A file that always lands at the root throws away what a filesystem is for:
progressive disclosure. So one fast-tier call reads the filename and picks a
folder — but only ever an *existing* one. Inventing folders per file is how a
stash ends up with forty folders holding one item each; growing the ontology
is a decision for the user, not a side effect of an upload.

The suggestion is advisory. A file that cannot be classified belongs at the
root, which is exactly where it lands today, and a classifier that is slow,
broken, or unconfigured must never cost someone their upload — so failures
here are logged loudly and the drop proceeds unfiled.
"""

import logging
from uuid import UUID

from ..database import get_pool
from . import llm

logger = logging.getLogger(__name__)

# Past this many folders the prompt stops being cheap and the choice stops
# being meaningful; the deepest paths are also the least likely destinations.
MAX_CANDIDATES = 60

_SYSTEM = (
    "You file documents into an existing folder structure. You never invent "
    "folders and you never guess: filing something wrongly is worse than "
    "leaving it unfiled, because a person can always find what is at the top "
    "level but will not think to look in the wrong folder."
)

_PROMPT = """Here are the folders in this person's filesystem:

{folders}

A file named "{filename}" ({content_type}) has just been added.

Which folder does it clearly belong in? Reply with JSON:
{{"folder": "<exact path from the list>"}} or {{"folder": null}}

Choose null unless the fit is obvious from the filename. A generic name
(screenshot, untitled, document, image, scan) is never obvious."""


async def _candidates(owner_user_id: UUID) -> list[dict]:
    """Foldable folders and their paths. Reserved spaces (Memory), protected
    folders, and skills are the product's structure, not filing destinations."""
    rows = await get_pool().fetch(
        """
        WITH RECURSIVE tree AS (
            SELECT id, name::text AS path, is_memory, is_protected, is_skill
            FROM folders WHERE owner_user_id = $1 AND parent_folder_id IS NULL
            UNION ALL
            SELECT f.id, tree.path || '/' || f.name, f.is_memory, f.is_protected, f.is_skill
            FROM folders f JOIN tree ON f.parent_folder_id = tree.id
            WHERE f.owner_user_id = $1
        )
        SELECT id, path FROM tree
        WHERE NOT is_memory AND NOT is_protected AND NOT is_skill
        ORDER BY length(path) - length(replace(path, '/', '')), path
        LIMIT $2
        """,
        owner_user_id,
        MAX_CANDIDATES,
    )
    return [dict(r) for r in rows]


async def suggest_folder(
    owner_user_id: UUID, filename: str, content_type: str
) -> tuple[UUID | None, str | None]:
    """(folder_id, path) for a dropped file, or (None, None) for the top level."""
    candidates = await _candidates(owner_user_id)
    if not candidates:
        # Nothing to choose from: an empty filesystem has no opinion yet.
        return None, None

    by_path = {c["path"]: c["id"] for c in candidates}
    try:
        answer = await llm.complete_json(
            system=_SYSTEM,
            prompt=_PROMPT.format(
                folders="\n".join(f"- {path}" for path in by_path),
                filename=filename,
                content_type=content_type,
            ),
            max_tokens=200,
        )
    except Exception as exc:
        # Advisory, not required: an upload must not fail because filing did.
        logger.warning(
            "file_classifier: suggestion failed filename=%s exception_type=%s",
            filename,
            type(exc).__name__,
        )
        return None, None

    chosen = answer.get("folder")
    if chosen is None:
        return None, None
    if chosen not in by_path:
        # The model named a folder that does not exist — the one thing the
        # prompt forbids. Loud, because it means the prompt has drifted.
        logger.warning("file_classifier: invented folder %r for %s", chosen, filename)
        return None, None
    return by_path[chosen], chosen
