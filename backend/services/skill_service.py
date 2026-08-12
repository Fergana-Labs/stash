"""Skill service — a skill is a folder whose ``is_skill`` flag is set.

Membership is stored, never derived: it changes only through deliberate
verbs (create a skill, convert a folder, import a repo), so editing files
inside a folder can never reclassify it. SKILL.md still holds the skill's
instructions and frontmatter metadata — a skill missing it is a draft that
says so, not a folder that quietly stopped being a skill.

Files and Skills are MECE: skill subtrees are filtered out of every Files
surface (see ``skill_subtree_folder_ids``) and surfaced in the Skills area
instead. Publishing/sharing attaches a 1:1 ``skills`` row to the folder
(shared_skill_service).
"""

from __future__ import annotations

import json
from uuid import UUID

from ..database import get_pool
from . import permission_service

SKILL_MD_NAME = "SKILL.md"
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024

# How many not-yet-skill documents a shelf names before the rest are just a count.
NOT_SKILLS_NAMED = 5

# How much of a document is read to decide whether it declares itself a skill.
# Listing and counting work from a prefix so a shelf of scanned catalogues does
# not cross the wire; reading applies the same bound so all three agree on what
# a skill is. `name` and `description` are capped, but `when_to_use` and
# `version` are not, so this has to be roomy — past it, a frontmatter block is
# not frontmatter.
FRONTMATTER_SCAN_BYTES = 8192


def skill_md_template(name: str, description: str) -> str:
    return (
        f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description)}\n---\n\n# {name}\n"
    )


def not_skill_folder_pred(alias: str) -> str:
    """SQL fragment: folder ``alias`` is not a skill."""
    return f"NOT {alias}.is_skill"


async def skill_subtree_folder_ids(owner_user_id: UUID) -> set[UUID]:
    """Every folder inside any skill subtree: the SKILL.md folders themselves
    plus all their descendants. Used to keep Files surfaces skill-free."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH RECURSIVE skill_tree AS ("
        "  SELECT f.id FROM folders f WHERE f.owner_user_id = $1 AND f.is_skill"
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
            meta[key] = json.loads(val)
        else:
            meta[key] = val
    return meta, body


def validate_skill_md(md: str) -> None:
    meta, _body = parse_frontmatter(md)
    name = str(meta.get("name", "")).strip()
    description = str(meta.get("description", "")).strip()
    if not name:
        raise ValueError("SKILL.md frontmatter requires a nonblank name")
    if len(name) > MAX_SKILL_NAME_LENGTH:
        raise ValueError(f"SKILL.md name must be at most {MAX_SKILL_NAME_LENGTH} characters")
    if not description:
        raise ValueError("SKILL.md frontmatter requires a nonblank description")
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        raise ValueError(
            f"SKILL.md description must be at most {MAX_SKILL_DESCRIPTION_LENGTH} characters"
        )


def declared_skill(content: str | None) -> dict | None:
    """The frontmatter of a document that declares itself a skill, or None.

    A document in a bound folder is a skill only if it carries the same
    frontmatter block every other SKILL.md carries, and passes the same
    validator. Nothing is derived from its title or its first line: a rule that
    always succeeds cannot tell a skill from a shopping list, and the folder
    holds both. Everything else in there stays ordinary source material —
    indexed, readable, searchable, and out of the agent's catalogue.
    """
    try:
        validate_skill_md(content or "")
    except ValueError:
        return None
    meta, _body = parse_frontmatter(content or "")
    return meta


def source_document_skill_status(content: str | None, extraction_status: str) -> dict[str, str]:
    """Explain whether one document in a bound Drive folder is a Skill."""
    if extraction_status in ("pending", "processing"):
        return {
            "skill_status": "checking",
            "skill_status_reason": "Stash is still reading this file.",
        }

    if extraction_status == "failed":
        return {
            "skill_status": "not_skill",
            "skill_status_reason": "Stash could not read this file.",
        }

    if extraction_status == "unsupported":
        return {
            "skill_status": "not_skill",
            "skill_status_reason": "Stash cannot read this file type.",
        }

    head = (content or "")[:FRONTMATTER_SCAN_BYTES]
    if declared_skill(head) is None:
        return {
            "skill_status": "not_skill",
            "skill_status_reason": "At the top, add a name and description between --- lines.",
        }

    if not parse_frontmatter(head)[1].strip():
        return {
            "skill_status": "draft",
            "skill_status_reason": "Add instructions below the closing --- line.",
        }

    return {
        "skill_status": "skill",
        "skill_status_reason": "Agents can load this file as a Skill.",
    }


async def count_shelf_skills(owner_user_id: UUID, source_ids: list[str]) -> dict[str, dict]:
    """Per bound source: how many of its documents are skills, and how many
    documents it holds.

    Counted only for the folders named in `source_ids`. Seeded at zero so a
    folder that has not been filled still reports itself.

    Both numbers, because only the pair is legible. A shelf reporting "3
    skills" when it holds 7 documents is the difference between a working bind
    and four documents whose authors forgot the frontmatter block — and
    without it, a document that isn't a skill just silently isn't there.

    Reads a prefix of each document rather than its body: frontmatter is at the
    top, and a shelf of scanned catalogues is a lot of bytes to pull for a
    counting query.
    """
    counts: dict[str, dict] = {
        source_id: {"skills": 0, "documents": 0, "not_skills": []} for source_id in source_ids
    }
    if not source_ids:
        return counts
    rows = await get_pool().fetch(
        # The head is materialised only for documents that could possibly be
        # skills. A shelf is mostly ordinary material, and pulling a prefix of
        # every scanned catalogue to discover it isn't one is pure waste.
        "SELECT d.source_id, d.name, "
        f"  CASE WHEN d.content LIKE '---%' THEN left(d.content, {FRONTMATTER_SCAN_BYTES}) END AS head "
        "FROM drive_documents d "
        "JOIN user_sources src ON src.id = d.source_id "
        "WHERE d.owner_user_id = $1 AND d.deleted_at IS NULL AND src.binds_skills "
        "  AND d.source_id = ANY($2::uuid[]) "
        "ORDER BY d.name",
        owner_user_id,
        source_ids,
    )
    for row in rows:
        tally = counts[str(row["source_id"])]
        tally["documents"] += 1
        if row["head"] is not None and declared_skill(row["head"]) is not None:
            tally["skills"] += 1
        elif len(tally["not_skills"]) < NOT_SKILLS_NAMED:
            # Named, not just counted: "1 of 2" tells you something is wrong
            # and leaves you hunting for which document to go fix. Only the
            # first few — the rest are a number, not a list, and a shelf of
            # thousands would otherwise put every filename on the wire.
            tally["not_skills"].append(row["name"])
    return counts


async def list_source_skills(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """Every document in a skill-binding source that declares itself a skill."""
    readable = permission_service.readable_content_condition("source", "src", 2)
    rows = await get_pool().fetch(
        # Only the frontmatter is needed to list a skill, and only a document
        # that starts with a delimiter can carry any — so the shelf's bodies
        # stay in the database instead of crossing the wire to be discarded.
        f"SELECT d.external_ref, d.name, left(d.content, {FRONTMATTER_SCAN_BYTES}) AS head, "
        "  d.updated_at, src.display_name AS source_name "
        "FROM drive_documents d "
        "JOIN user_sources src ON src.id = d.source_id "
        "WHERE d.owner_user_id = $1 AND d.deleted_at IS NULL AND src.binds_skills "
        f"  AND d.content LIKE '---%' AND {readable} "
        # A document with no upstream id has no stable address, so it cannot be
        # offered as a skill. The Drive walk always records one.
        "  AND d.external_ref IS NOT NULL "
        "ORDER BY d.name",
        owner_user_id,
        user_id,
    )
    declared = [(r, declared_skill(r["head"])) for r in rows]
    return [
        {
            "folder_id": None,
            "source_ref": r["external_ref"],
            "backing": "source",
            "source_name": r["source_name"],
            "name": meta["name"],
            "description": meta["description"],
            "when_to_use": meta.get("when_to_use", ""),
            "version": meta.get("version", ""),
            "mcp_exposed": bool(meta.get("mcp_exposed", False)),
            "file_count": 1,
            "updated_at": r["updated_at"],
            # A document can declare itself and then say nothing. Handing an
            # agent an empty skill is the failure the draft flag exists to
            # stop, so a frontmatter block with no body below it is a draft.
            "has_instructions": bool(parse_frontmatter(r["head"])[1].strip()),
            # Publishing attaches a `skills` row to a folder id, which a
            # source-backed skill does not have. It is managed upstream.
            "published": None,
        }
        for r, meta in declared
        if meta is not None
    ]


async def list_skills(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """List every skill folder in the scope: folder + SKILL.md frontmatter,
    plus the publish record when the skill has been shared.

    LEFT JOIN on SKILL.md, not INNER: membership is the flag, so a skill
    whose instructions are missing still lists — as a draft, with
    has_instructions false — instead of vanishing from every surface."""
    pool = get_pool()
    readable = permission_service.readable_content_condition("folder", "f", 2)
    rows = await pool.fetch(
        "SELECT f.id AS folder_id, f.name AS folder_name, f.updated_at AS folder_updated_at, "
        "  p.id AS skill_md_id, p.content_markdown AS skill_md, p.updated_at, "
        "  (SELECT COUNT(*) FROM pages p2 WHERE p2.folder_id = f.id "
        "   AND p2.deleted_at IS NULL) AS file_count, "
        "  s.id AS publish_id, s.slug, s.title, s.discoverable, "
        "  s.cover_image_url, s.icon_url, s.view_count "
        "FROM folders f "
        "LEFT JOIN pages p ON p.folder_id = f.id AND p.name = 'SKILL.md' AND p.deleted_at IS NULL "
        "LEFT JOIN skills s ON s.folder_id = f.id "
        f"WHERE f.owner_user_id = $1 AND f.is_skill AND {readable} "
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
                "source_ref": None,
                "backing": "folder",
                "source_name": None,
                "name": meta.get("name") or r["folder_name"],
                "description": meta.get("description", ""),
                "when_to_use": meta.get("when_to_use", ""),
                "version": meta.get("version", ""),
                "mcp_exposed": bool(meta.get("mcp_exposed", False)),
                "file_count": int(r["file_count"]),
                "updated_at": r["updated_at"] or r["folder_updated_at"],
                # False = a draft skill: it exists and is named, but has no
                # instructions for an agent to load yet. Surfaces say so.
                "has_instructions": r["skill_md_id"] is not None,
                "published": published,
            }
        )
    out.extend(await list_source_skills(owner_user_id, user_id))
    out.sort(key=lambda s: s["name"].lower())
    return out


async def read_source_skill(owner_user_id: UUID, source_ref: str, user_id: UUID) -> dict | None:
    """Read a source-backed skill: the upstream document is the instructions.

    Addressed by `source_ref` — the upstream file's own id — because our row is
    keyed on the document's path and is therefore destroyed and recreated when
    its author renames it in Drive. The file id survives that; a row id does
    not, and a skill's address must outlive a rename.

    A document that does not declare itself a skill reads as None — it is not
    a broken skill, it is a file that happens to live on the shelf, and the
    caller 404s rather than dressing it up as one.
    """
    readable = permission_service.readable_content_condition("source", "src", 3)
    row = await get_pool().fetchrow(
        "SELECT d.external_ref, d.name, d.content, d.updated_at, "
        "  src.display_name AS source_name "
        "FROM drive_documents d "
        "JOIN user_sources src ON src.id = d.source_id "
        "WHERE d.owner_user_id = $1 AND d.external_ref = $2 AND d.deleted_at IS NULL "
        f"  AND src.binds_skills AND {readable} "
        # A Drive shortcut resolves to its target's file id, so a shortcut
        # sitting near its target puts that id on two rows. They are the same
        # upstream document, so either answers the read — ordered so the answer
        # is at least the same one every time.
        "ORDER BY d.path LIMIT 1",
        owner_user_id,
        source_ref,
        user_id,
    )
    if row is None:
        return None
    # The same bound the listing works from: a block that only resolves in the
    # full document would make a skill that reads but never lists.
    meta = declared_skill((row["content"] or "")[:FRONTMATTER_SCAN_BYTES])
    if meta is None:
        return None
    _meta, body = parse_frontmatter(row["content"] or "")
    return {
        "folder_id": None,
        "source_ref": row["external_ref"],
        "backing": "source",
        "source_name": row["source_name"],
        "name": meta["name"],
        "description": meta["description"],
        "when_to_use": meta.get("when_to_use", ""),
        "has_instructions": bool(body.strip()),
        "body": body,
        "files": [
            {
                "id": row["external_ref"],
                "name": row["name"],
                "updated_at": row["updated_at"],
                "content": body,
            }
        ],
        "combined": f"# {meta['name']}\n\n{body}" if body.strip() else "",
    }


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

    if match["backing"] == "source":
        return await read_source_skill(owner_user_id, match["source_ref"], user_id)

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
        "source_ref": None,
        "backing": "folder",
        "name": match["name"],
        "description": match["description"],
        "when_to_use": match["when_to_use"],
        # A draft skill loads with no instructions. Callers that need them
        # (agent load, publish, install) refuse on this rather than handing
        # an agent an empty document and calling it a skill.
        "has_instructions": skill_md is not None,
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
