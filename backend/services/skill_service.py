"""Skill service — skills are folders explicitly classified by a ``skills`` row.

A folder is a skill iff a ``skills`` record (slug, title, Discover flag, cover
art — shared_skill_service) points at it. Classification never depends on
whether a SKILL.md page exists. Files and Skills are MECE: skill subtrees are
filtered out of every Files surface (see ``skill_subtree_folder_ids``) and
surfaced in the Skills area instead. Public readability is a public share on
the folder, like any other resource.
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool
from . import permission_service

SKILL_MD_NAME = "SKILL.md"


def not_skill_folder_pred(alias: str) -> str:
    """SQL fragment: folder ``alias`` is not classified as a skill."""
    return f"NOT EXISTS (SELECT 1 FROM skills sk WHERE sk.folder_id = {alias}.id)"


async def skill_subtree_folder_ids(owner_user_id: UUID) -> set[UUID]:
    """Every folder inside any skill subtree: the classified folders themselves
    plus all their descendants. Used to keep Files surfaces skill-free."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE skill_tree AS ("
        "  SELECT f.id FROM folders f "
        "  WHERE f.owner_user_id = $1 "
        "    AND EXISTS (SELECT 1 FROM skills sk WHERE sk.folder_id = f.id)"
        "  UNION"
        "  SELECT f.id FROM folders f JOIN skill_tree st ON f.parent_folder_id = st.id"
        ") SELECT id FROM skill_tree",
        owner_user_id,
    )
    return {r["id"] for r in rows}


def parse_frontmatter(md: str) -> tuple[dict, str]:
    """Tiny YAML-ish frontmatter parser. Supports `key: value` only — no nested
    structures, lists, or quoted-with-escapes. That's deliberate: skill metadata
    is supposed to be flat. Returns (metadata, body)."""
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    raw = md[3:end].strip("\n")
    body = md[end + 4 :].lstrip("\n")
    meta: dict = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.lower() in ("true", "false"):
            meta[key] = val.lower() == "true"
        elif val.startswith('"') and val.endswith('"'):
            meta[key] = val[1:-1]
        else:
            meta[key] = val
    return meta, body


async def list_skills(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """List every skill in the scope: the record, the folder, SKILL.md
    frontmatter when present, and whether the folder is publicly shared."""
    pool = get_pool()
    readable = permission_service.readable_content_condition("folder", "f", 2)
    rows = await pool.fetch(
        "SELECT f.id AS folder_id, f.name AS folder_name, "
        "  p.content_markdown AS skill_md, "
        "  COALESCE(p.updated_at, f.updated_at) AS updated_at, "
        "  (SELECT COUNT(*) FROM pages p2 WHERE p2.folder_id = f.id "
        "   AND p2.deleted_at IS NULL) AS file_count, "
        "  s.id AS skill_id, s.slug, s.title, s.discoverable, "
        "  s.cover_image_url, s.icon_url, s.view_count, "
        "  EXISTS (SELECT 1 FROM shares pub WHERE pub.object_type = 'folder' "
        "   AND pub.object_id = f.id AND pub.principal_type = 'public') AS public "
        "FROM skills s "
        "JOIN folders f ON f.id = s.folder_id "
        "LEFT JOIN pages p ON p.folder_id = f.id AND p.name = 'SKILL.md' "
        "  AND p.deleted_at IS NULL "
        f"WHERE f.owner_user_id = $1 AND {readable} "
        "ORDER BY f.name",
        owner_user_id,
        user_id,
    )
    out = []
    for r in rows:
        meta, _body = parse_frontmatter(r["skill_md"] or "")
        out.append(
            {
                "folder_id": str(r["folder_id"]),
                "name": meta.get("name") or r["folder_name"],
                "description": meta.get("description", ""),
                "when_to_use": meta.get("when_to_use", ""),
                "version": meta.get("version", ""),
                "mcp_exposed": bool(meta.get("mcp_exposed", False)),
                "file_count": int(r["file_count"]),
                "updated_at": r["updated_at"],
                "public": bool(r["public"]),
                "skill": {
                    "id": str(r["skill_id"]),
                    "slug": r["slug"],
                    "title": r["title"],
                    "discoverable": bool(r["discoverable"]),
                    "cover_image_url": r["cover_image_url"],
                    "icon_url": r["icon_url"],
                    "view_count": int(r["view_count"] or 0),
                },
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
