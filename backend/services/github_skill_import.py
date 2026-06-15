"""Import public GitHub repos containing SKILL.md folders as curated Skills.

Every directory whose immediate children include a SKILL.md (the repo root
counts) becomes one published, discoverable skill in the curator workspace,
attributed via skills.source_github_url. Re-imports are idempotent: skills
are matched by source_github_url and their folder contents replaced in
place, so the slug and view count survive upstream updates.

Run via scripts/import_github_skills.py.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from uuid import UUID

import httpx

from ..auth import hash_password
from ..database import get_pool
from . import files_tree_service, shared_skill_service, skill_service

logger = logging.getLogger(__name__)

CURATOR_USERNAME = "stash-curated"
CURATOR_WORKSPACE_NAME = "Stash Curated"
MAX_FILE_BYTES = 50 * 1024 * 1024  # matches the upload endpoint's limit

_REPO_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_API = "https://api.github.com"
_RAW = "https://raw.githubusercontent.com"


def parse_repo_url(url: str) -> tuple[str, str]:
    match = _REPO_URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"Not a GitHub repo URL: {url}")
    return match.group(1), match.group(2)


def source_url(owner: str, repo: str, branch: str, skill_dir: str) -> str:
    """Canonical attribution URL — also the idempotency key for re-imports."""
    if not skill_dir:
        return f"https://github.com/{owner}/{repo}"
    return f"https://github.com/{owner}/{repo}/tree/{branch}/{skill_dir}"


def discover_skill_dirs(tree: list[dict]) -> list[str]:
    """Directories whose immediate children include SKILL.md ('' = repo root)."""
    dirs = []
    for entry in tree:
        if entry["type"] != "blob":
            continue
        path = entry["path"]
        if path == "SKILL.md":
            dirs.append("")
        elif path.endswith("/SKILL.md"):
            dirs.append(path[: -len("/SKILL.md")])
    return sorted(dirs)


# ===== GitHub fetchers (monkeypatched in tests) =====


def _api_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _fetch_default_branch(client: httpx.AsyncClient, owner: str, repo: str) -> str:
    resp = await client.get(f"{_API}/repos/{owner}/{repo}", headers=_api_headers())
    resp.raise_for_status()
    return resp.json()["default_branch"]


async def _fetch_tree(client: httpx.AsyncClient, owner: str, repo: str, ref: str) -> list[dict]:
    resp = await client.get(
        f"{_API}/repos/{owner}/{repo}/git/trees/{ref}",
        params={"recursive": "1"},
        headers=_api_headers(),
    )
    resp.raise_for_status()
    return resp.json()["tree"]


async def _fetch_blob(
    client: httpx.AsyncClient, owner: str, repo: str, ref: str, path: str
) -> bytes:
    # raw.githubusercontent.com serves blobs without burning API rate limit.
    resp = await client.get(f"{_RAW}/{owner}/{repo}/{ref}/{path}")
    resp.raise_for_status()
    return resp.content


async def fetch_repo_skills(repo_url: str) -> list[dict]:
    """Fetch every skill in a repo: [{source_url, fallback_title, files}]
    where files is [(path relative to the skill dir, bytes)]."""
    owner, repo = parse_repo_url(repo_url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        branch = await _fetch_default_branch(client, owner, repo)
        tree = await _fetch_tree(client, owner, repo, branch)
        skills = []
        for skill_dir in discover_skill_dirs(tree):
            prefix = f"{skill_dir}/" if skill_dir else ""
            files = []
            for entry in tree:
                if entry["type"] != "blob" or not entry["path"].startswith(prefix):
                    continue
                if entry.get("size", 0) > MAX_FILE_BYTES:
                    logger.warning(
                        "skipping oversized file %s (%s bytes)", entry["path"], entry["size"]
                    )
                    continue
                blob = await _fetch_blob(client, owner, repo, branch, entry["path"])
                files.append((entry["path"][len(prefix) :], blob))
            skills.append(
                {
                    "source_url": source_url(owner, repo, branch, skill_dir),
                    "fallback_title": skill_dir.rsplit("/", 1)[-1] if skill_dir else repo,
                    "files": files,
                }
            )
        return skills


# ===== Import into the curator workspace =====


async def ensure_curator() -> tuple[UUID, UUID]:
    """Ensure the curator system user and workspace exist.

    Returns (workspace_id, owner_id). Idempotent — mirrors
    demo_service.seed_demo_workspace.
    """
    pool = get_pool()
    owner_id = await pool.fetchval("SELECT id FROM users WHERE name = $1", CURATOR_USERNAME)
    if owner_id is None:
        # Random unrecoverable password — this account is never logged into;
        # the import script operates as it via the services directly.
        pw_hash = hash_password(secrets.token_urlsafe(32))
        owner_id = await pool.fetchval(
            "INSERT INTO users (name, display_name, password_hash, description) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            CURATOR_USERNAME,
            "Stash",
            pw_hash,
            "System user that owns GitHub-imported Discover skills.",
        )
        logger.info("created curator system user %s", owner_id)

    workspace_id = await pool.fetchval(
        "SELECT w.id FROM workspaces w "
        "JOIN workspace_members wm ON wm.workspace_id = w.id "
        "WHERE wm.user_id = $1 AND w.name = $2 LIMIT 1",
        owner_id,
        CURATOR_WORKSPACE_NAME,
    )
    if workspace_id is None:
        invite_code = secrets.token_urlsafe(6)[:8]
        workspace_id = await pool.fetchval(
            "INSERT INTO workspaces (name, description, creator_id, invite_code) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            CURATOR_WORKSPACE_NAME,
            "Curated public skills imported from GitHub for Discover.",
            owner_id,
            invite_code,
        )
        await pool.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role, is_primary) "
            "VALUES ($1, $2, 'owner', false)",
            workspace_id,
            owner_id,
        )
        logger.info("created curator workspace %s", workspace_id)
    return workspace_id, owner_id


async def import_skill(
    workspace_id: UUID,
    owner_id: UUID,
    *,
    source_url: str,
    fallback_title: str,
    files: list[tuple[str, bytes]],
) -> str:
    """Import one skill's files. Returns 'created' or 'updated'."""
    skill_md = next((blob for path, blob in files if path == "SKILL.md"), None)
    if skill_md is None:
        raise ValueError(f"{source_url}: no SKILL.md")
    meta, _body = skill_service.parse_frontmatter(skill_md.decode("utf-8", errors="replace"))
    title = str(meta.get("name") or fallback_title)
    description = str(meta.get("description") or "")

    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT id, folder_id FROM skills WHERE source_github_url = $1", source_url
    )
    if existing:
        await files_tree_service.clear_folder_contents(existing["folder_id"])
        await files_tree_service.write_folder_files(
            workspace_id, owner_id, existing["folder_id"], files
        )
        await pool.execute(
            "UPDATE skills SET title = $1, description = $2, updated_at = now() WHERE id = $3",
            title,
            description,
            existing["id"],
        )
        return "updated"

    folder_id = await _create_root_folder(workspace_id, owner_id, title)
    await files_tree_service.write_folder_files(workspace_id, owner_id, folder_id, files)
    await shared_skill_service.publish_folder(
        workspace_id,
        owner_id,
        folder_id,
        title=title,
        description=description,
        discoverable=True,
        source_github_url=source_url,
    )
    return "created"


async def _create_root_folder(workspace_id: UUID, owner_id: UUID, title: str) -> UUID:
    # Skills from different repos can share a title; folder names are unique
    # per parent, so suffix like fork_skill does.
    name = title
    for n in range(2, 50):
        try:
            folder = await files_tree_service.create_folder(
                workspace_id=workspace_id, name=name, created_by=owner_id
            )
            return folder["id"]
        except files_tree_service.DuplicateFolderName:
            name = f"{title} ({n})"
    raise ValueError(f"Could not find a free folder name for {title!r}")


# ===== Whole-repo operations (script + admin dashboard) =====


async def import_repo(repo_url: str) -> dict:
    """Import every SKILL.md folder in a repo into the curator workspace.

    Returns a summary: how many skills the repo had and how many were newly
    created vs updated in place. Idempotent — re-running tracks upstream."""
    workspace_id, owner_id = await ensure_curator()
    skills = await fetch_repo_skills(repo_url)
    created = updated = 0
    for skill in skills:
        result = await import_skill(
            workspace_id,
            owner_id,
            source_url=skill["source_url"],
            fallback_title=skill["fallback_title"],
            files=skill["files"],
        )
        created += result == "created"
        updated += result == "updated"
    return {
        "repo_url": repo_url,
        "skills_found": len(skills),
        "created": created,
        "updated": updated,
    }


def _repo_base(source_github_url: str) -> str:
    """github.com/owner/repo from a skill's source URL (drops any /tree/... suffix)."""
    return "/".join(source_github_url.split("/")[:5])


async def list_imported_repos() -> list[dict]:
    """Every imported skill, grouped by source repo — for the admin dashboard."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT source_github_url, title, slug, updated_at FROM skills "
        "WHERE source_github_url IS NOT NULL ORDER BY source_github_url"
    )
    repos: dict[str, dict] = {}
    for r in rows:
        base = _repo_base(r["source_github_url"])
        repo = repos.setdefault(base, {"repo_url": base, "skills": []})
        repo["skills"].append(
            {
                "title": r["title"],
                "slug": r["slug"],
                "source_github_url": r["source_github_url"],
                "updated_at": r["updated_at"].isoformat(),
            }
        )
    return sorted(repos.values(), key=lambda r: r["repo_url"])


async def remove_repo_skills(repo_url: str) -> int:
    """Delete every imported skill from a repo. Returns the count removed.

    Deleting the root folder cascades the skills row (folder_id FK); we clear
    the subtree first so child pages/files (folder FK SET NULL) don't orphan."""
    owner, repo = parse_repo_url(repo_url)
    base = f"https://github.com/{owner}/{repo}"
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT folder_id FROM skills " "WHERE source_github_url = $1 OR source_github_url LIKE $2",
        base,
        f"{base}/tree/%",
    )
    for r in rows:
        await files_tree_service.clear_folder_contents(r["folder_id"])
        await pool.execute("DELETE FROM folders WHERE id = $1", r["folder_id"])
    return len(rows)
