"""Skill service — skills are special folders containing a SKILL.md file.

Detection rule: any folder whose immediate children include a page named
``SKILL.md``. Skill-ness is derived, never stored; reads/writes go through
the Files API. Files and Skills are MECE: skill subtrees are filtered out of
every Files surface (see ``skill_subtree_folder_ids``) and surfaced in the
Skills area instead. Publishing/sharing attaches a 1:1 ``skills`` row to the
folder (shared_skill_service).
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool
from . import permission_service

SKILL_MD_NAME = "SKILL.md"


def not_skill_folder_pred(alias: str) -> str:
    """SQL fragment: folder ``alias`` has no live SKILL.md child."""
    return (
        f"NOT EXISTS (SELECT 1 FROM pages skp WHERE skp.folder_id = {alias}.id "
        "AND skp.name = 'SKILL.md' AND skp.deleted_at IS NULL)"
    )


async def skill_subtree_folder_ids(owner_user_id: UUID) -> set[UUID]:
    """Every folder inside any skill subtree: the SKILL.md folders themselves
    plus all their descendants. Used to keep Files surfaces skill-free."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE skill_tree AS ("
        "  SELECT f.id FROM folders f "
        "  WHERE f.owner_user_id = $1 "
        "    AND EXISTS (SELECT 1 FROM pages p WHERE p.folder_id = f.id "
        "                AND p.name = 'SKILL.md' AND p.deleted_at IS NULL)"
        "  UNION"
        "  SELECT f.id FROM folders f JOIN skill_tree st ON f.parent_folder_id = st.id"
        ") SELECT id FROM skill_tree",
        owner_user_id,
    )
    return {r["id"] for r in rows}


def _scalar(val: str):
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    return val


def parse_frontmatter(md: str) -> tuple[dict, str]:
    """Tiny YAML-ish frontmatter parser. Supports `key: value` and one level of
    block list (`key:` followed by `- item` lines) — no deeper nesting, no
    quoted-with-escapes. Skill metadata stays flat apart from `examples`, the
    starter prompts the Skills launcher offers. A bare `key:` with nothing
    listed under it stays the empty string it has always been.
    Returns (metadata, body)."""
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    raw = md[3:end].strip("\n")
    body = md[end + 4 :].lstrip("\n")
    lines = raw.splitlines()
    meta: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val:
            meta[key] = _scalar(val)
            continue
        items = []
        while i < len(lines) and lines[i].strip().startswith("- "):
            items.append(_scalar(lines[i].strip()[2:].strip()))
            i += 1
        meta[key] = items if items else ""
    return meta, body


def frontmatter_examples(meta: dict) -> list[str]:
    """The skill's starter prompts. A skill that declares none has none — the
    launcher composes a prompt from the skill name instead."""
    raw = meta.get("examples")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


async def list_skills(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """List every skill folder in the scope: folder + SKILL.md frontmatter,
    plus the publish record when the skill has been shared."""
    pool = get_pool()
    readable = permission_service.readable_content_condition("folder", "f", 2)
    rows = await pool.fetch(
        "SELECT f.id AS folder_id, f.name AS folder_name, "
        "  p.id AS skill_md_id, p.content_markdown AS skill_md, p.updated_at, "
        "  (SELECT COUNT(*) FROM pages p2 WHERE p2.folder_id = f.id "
        "   AND p2.deleted_at IS NULL) AS file_count, "
        "  s.id AS publish_id, s.slug, s.title, s.discoverable, "
        "  s.cover_image_url, s.icon_url, s.view_count "
        "FROM folders f "
        "JOIN pages p ON p.folder_id = f.id AND p.name = 'SKILL.md' AND p.deleted_at IS NULL "
        "LEFT JOIN skills s ON s.folder_id = f.id "
        f"WHERE f.owner_user_id = $1 AND {readable} "
        "ORDER BY f.name",
        owner_user_id,
        user_id,
    )
    out = []
    for r in rows:
        meta, _body = parse_frontmatter(r["skill_md"] or "")
        published = None
        if r["publish_id"]:
            published = {
                "id": str(r["publish_id"]),
                "slug": r["slug"],
                "discoverable": bool(r["discoverable"]),
                "cover_image_url": r["cover_image_url"],
                "icon_url": r["icon_url"],
                "view_count": int(r["view_count"] or 0),
            }
        out.append(
            {
                "folder_id": str(r["folder_id"]),
                "name": meta.get("name") or r["folder_name"],
                "description": meta.get("description", ""),
                "when_to_use": meta.get("when_to_use", ""),
                "examples": frontmatter_examples(meta),
                "version": meta.get("version", ""),
                "mcp_exposed": bool(meta.get("mcp_exposed", False)),
                "file_count": int(r["file_count"]),
                "updated_at": r["updated_at"],
                "published": published,
            }
        )
    return out


async def read_skill(owner_user_id: UUID, name: str, user_id: UUID) -> dict | None:
    """Read a skill by its frontmatter name OR its folder name. Returns the
    parsed SKILL.md plus the full text of every sibling file concatenated, so
    an agent can load the whole skill in one call."""
    pool = get_pool()
    skills = await list_skills(owner_user_id, user_id)
    match = next(
        (s for s in skills if s["name"] == name or s["folder_id"] == name),
        None,
    )
    if not match:
        # Fall back to folder name match (case-insensitive)
        match = next(
            (s for s in skills if s["name"].lower() == name.lower()),
            None,
        )
    if not match:
        return None

    folder_id = match["folder_id"]
    pages = await pool.fetch(
        "SELECT id, name, content_markdown, updated_at "
        "FROM pages WHERE folder_id = $1 AND deleted_at IS NULL ORDER BY name",
        UUID(folder_id),
    )
    readable_pages = []
    for page in pages:
        if await permission_service.check_access(
            "page",
            page["id"],
            user_id,
            owner_user_id=owner_user_id,
        ):
            readable_pages.append(page)
    pages = readable_pages

    skill_md = next((p for p in pages if p["name"] == "SKILL.md"), None)
    body = ""
    if skill_md:
        _meta, body = parse_frontmatter(skill_md["content_markdown"] or "")

    siblings = [p for p in pages if p["name"] != "SKILL.md"]
    combined_parts = []
    if skill_md:
        combined_parts.append(f"# {match['name']} (SKILL.md)\n\n{body}")
    for p in siblings:
        combined_parts.append(f"\n\n## {p['name']}\n\n{p['content_markdown'] or ''}")

    return {
        "folder_id": folder_id,
        "name": match["name"],
        "description": match["description"],
        "when_to_use": match["when_to_use"],
        "body": body,
        "files": [
            {
                "id": str(p["id"]),
                "name": p["name"],
                "updated_at": p["updated_at"],
                "content": p["content_markdown"] or "",
            }
            for p in pages
        ],
        "combined": "".join(combined_parts),
    }
