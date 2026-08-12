"""AI-curated skills — the three slots the nightly curator owns.

The curator's other output, the Memory wiki, is pull: it helps only when an
agent thinks to search it. Skills are push — the harness loads every
SKILL.md description at session start — so a curated skill fires without the
agent knowing to look. This is the write surface for that second target.

Every invariant lives here rather than in the curator's prompt, so a prompt
regression degrades the skills' quality instead of reintroducing the sprawl
the cap exists to prevent:

- **Three slots.** Writing a fourth fails loud and must name the slot it
  replaces; the replaced skill goes to the trash.
- **A human edit adopts.** ``adopt`` clears the flag, the slot frees, and
  the skill becomes an ordinary hand-authored one.
- **The curator only writes what it owns.** ``write`` matches names against
  curated skills only, so an adopted skill can never be overwritten by the
  next night's run.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..database import get_pool
from . import files_tree_service, skill_service

MAX_CURATED_SKILLS = 3


def _skill_md(name: str, description: str, body: str) -> str:
    """The curated SKILL.md. `description` is the only text the harness
    matches on, so it carries the whole trigger; the body is read after."""
    md = (
        f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description)}\n"
        f"curated: true\n---\n\n{body.strip()}\n"
    )
    skill_service.validate_skill_md(md)
    return md


async def list_curated(owner_user_id: UUID) -> list[dict]:
    """The occupied slots, oldest first — what the curator reads before
    deciding whether tonight's candidate beats an incumbent."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT f.id, f.name, f.created_at, p.content_markdown, p.updated_at "
        "FROM folders f "
        "LEFT JOIN pages p ON p.folder_id = f.id AND p.name = $2 AND p.deleted_at IS NULL "
        "WHERE f.owner_user_id = $1 AND f.is_curated "
        "ORDER BY f.created_at",
        owner_user_id,
        skill_service.SKILL_MD_NAME,
    )
    out = []
    for r in rows:
        meta, body = skill_service.parse_frontmatter(r["content_markdown"] or "")
        out.append(
            {
                "folder_id": str(r["id"]),
                "name": meta.get("name") or r["name"],
                "description": meta.get("description", ""),
                "body": body,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"] or r["created_at"],
            }
        )
    return out


async def write(
    owner_user_id: UUID,
    user_id: UUID,
    name: str,
    description: str,
    body: str,
    replaces: str | None = None,
) -> dict:
    """Create or update a curated skill. Raises ValueError with a sentence the
    curator can act on when the write would break an invariant."""
    name = name.strip()
    description = description.strip()
    if not name:
        raise ValueError("name must not be blank")
    if not description:
        raise ValueError("description must not be blank — it is the skill's only trigger")
    if not body.strip():
        raise ValueError("body must not be blank")

    skill_md = _skill_md(name, description, body)
    curated = await list_curated(owner_user_id)

    existing = next((c for c in curated if c["name"].lower() == name.lower()), None)
    if existing:
        await _write_skill_md(owner_user_id, user_id, UUID(existing["folder_id"]), skill_md)
        return {"folder_id": existing["folder_id"], "name": name, "action": "updated"}

    await _refuse_if_adopted(owner_user_id, name)
    if len(curated) >= MAX_CURATED_SKILLS:
        await _evict(owner_user_id, user_id, curated, replaces)

    folder = await files_tree_service.create_skill(owner_user_id, user_id, name, description)
    await _set_is_curated(folder["id"], owner_user_id, True)
    await _write_skill_md(owner_user_id, user_id, folder["id"], skill_md)
    return {"folder_id": str(folder["id"]), "name": folder["name"], "action": "created"}


async def adopt(owner_user_id: UUID, folder_id: UUID) -> dict | None:
    """A human touched it, so it's theirs: the skill stops being curated and
    the slot frees. Returns None when the folder wasn't a curated skill —
    adopting twice is not an error, it's already adopted."""
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE folders SET is_curated = false, updated_at = now() "
        "WHERE id = $1 AND owner_user_id = $2 AND is_curated "
        "RETURNING id, name",
        folder_id,
        owner_user_id,
    )
    if row is None:
        return None
    return {"folder_id": str(row["id"]), "name": row["name"]}


async def _refuse_if_adopted(owner_user_id: UUID, name: str) -> None:
    """A skill by this name that isn't curated was written or adopted by the
    user. Writing it again would either overwrite their work or mint a
    near-duplicate ('Name (2)') that competes with it for the same trigger."""
    pool = get_pool()
    taken = await pool.fetchval(
        "SELECT name FROM folders "
        "WHERE owner_user_id = $1 AND is_skill AND NOT is_curated AND lower(name) = lower($2)",
        owner_user_id,
        name,
    )
    if taken:
        raise ValueError(
            f"{taken!r} is the user's own skill, not a curated one — "
            "they wrote it or adopted it. Leave it alone and pick another angle."
        )


async def _evict(
    owner_user_id: UUID, user_id: UUID, curated: list[dict], replaces: str | None
) -> None:
    slots = ", ".join(f"{c['name']!r}" for c in curated)
    if not replaces:
        raise ValueError(
            f"all {MAX_CURATED_SKILLS} curated slots are full ({slots}) — "
            "pass the name of the one this replaces, or leave the set alone"
        )
    target = next(
        (c for c in curated if replaces == c["folder_id"] or replaces.lower() == c["name"].lower()),
        None,
    )
    if target is None:
        raise ValueError(f"{replaces!r} is not a curated skill — the slots are {slots}")
    await files_tree_service.delete_folder(UUID(target["folder_id"]), owner_user_id, user_id)


async def _set_is_curated(folder_id: UUID, owner_user_id: UUID, is_curated: bool) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE folders SET is_curated = $3, updated_at = now() "
        "WHERE id = $1 AND owner_user_id = $2",
        folder_id,
        owner_user_id,
        is_curated,
    )


async def _write_skill_md(
    owner_user_id: UUID, user_id: UUID, folder_id: UUID, skill_md: str
) -> None:
    pool = get_pool()
    page_id = await pool.fetchval(
        "SELECT id FROM pages WHERE folder_id = $1 AND name = $2 AND deleted_at IS NULL",
        folder_id,
        skill_service.SKILL_MD_NAME,
    )
    if page_id is None:
        await files_tree_service.create_page(
            owner_user_id,
            skill_service.SKILL_MD_NAME,
            user_id,
            folder_id=folder_id,
            content=skill_md,
            content_type="markdown",
        )
        return
    await files_tree_service.update_page(page_id, owner_user_id, user_id, content=skill_md)
