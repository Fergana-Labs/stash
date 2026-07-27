"""GitHub repo imports.

Two flavors:
- User-facing (`import_repo_for_user`): straight copy of a whole repo into
  the caller's scope as one root folder. Folders containing SKILL.md derive
  as skills automatically. Uses the caller's GitHub connection when present,
  so private repos work too.
- Curator (`import_repo`, via scripts/import_github_skills.py): every
  directory whose immediate children include a SKILL.md becomes one
  published, discoverable skill in the curator scope, attributed via
  skills.source_github_url. Re-imports are idempotent: skills are matched by
  source_github_url and their folder contents replaced in place, so the slug
  and view count survive upstream updates.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from uuid import UUID

import httpx
from fastapi import HTTPException

from ..auth import hash_password
from ..database import get_pool
from ..integrations import storage as integration_storage
from . import files_tree_service, shared_skill_service, skill_service

logger = logging.getLogger(__name__)

CURATOR_USERNAME = "stash-curated"
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


def _api_headers(token: str | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _fetch_default_branch(
    client: httpx.AsyncClient, owner: str, repo: str, token: str | None = None
) -> str:
    resp = await client.get(f"{_API}/repos/{owner}/{repo}", headers=_api_headers(token))
    resp.raise_for_status()
    return resp.json()["default_branch"]


async def _fetch_tree(
    client: httpx.AsyncClient, owner: str, repo: str, ref: str, token: str | None = None
) -> list[dict]:
    resp = await client.get(
        f"{_API}/repos/{owner}/{repo}/git/trees/{ref}",
        params={"recursive": "1"},
        headers=_api_headers(token),
    )
    resp.raise_for_status()
    return resp.json()["tree"]


async def _fetch_blob(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    token: str | None = None,
) -> bytes:
    # raw.githubusercontent.com serves blobs without burning API rate limit;
    # with the user's token it serves their private repos too.
    resp = await client.get(f"{_RAW}/{owner}/{repo}/{ref}/{path}", headers=_api_headers(token))
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


async def fetch_repo_files(repo_url: str, token: str | None = None) -> tuple[str, list]:
    """Every blob in a repo, paths relative to the repo root.
    Returns (repo name, [(path, bytes)])."""
    owner, repo = parse_repo_url(repo_url)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        branch = await _fetch_default_branch(client, owner, repo, token)
        tree = await _fetch_tree(client, owner, repo, branch, token)
        files = []
        for entry in tree:
            if entry["type"] != "blob":
                continue
            if entry.get("size", 0) > MAX_FILE_BYTES:
                logger.warning(
                    "skipping oversized file %s (%s bytes)", entry["path"], entry["size"]
                )
                continue
            files.append(
                (
                    entry["path"],
                    await _fetch_blob(client, owner, repo, branch, entry["path"], token),
                )
            )
        return repo, files


async def inspect_repo(repo_url: str, token: str | None = None) -> list[str]:
    """Which directories in the repo are skills (contain a SKILL.md), without
    downloading any blobs — the pre-import check behind the section-mismatch
    confirmation in the import dialog."""
    owner, repo = parse_repo_url(repo_url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        branch = await _fetch_default_branch(client, owner, repo, token)
        tree = await _fetch_tree(client, owner, repo, branch, token)
    return discover_skill_dirs(tree)


# ===== Import into the curator scope =====


async def ensure_curator() -> tuple[UUID, UUID]:
    """Ensure the curator system user exists.

    Returns (owner_user_id, owner_id) — both the curator user id, since a user
    IS their own scope. Idempotent.
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
    return owner_id, owner_id


async def import_skill(
    owner_user_id: UUID,
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
            owner_user_id, owner_id, existing["folder_id"], files
        )
        await pool.execute(
            "UPDATE skills SET title = $1, description = $2, updated_at = now() WHERE id = $3",
            title,
            description,
            existing["id"],
        )
        return "updated"

    folder = await _create_root_folder(owner_user_id, owner_id, title)
    await files_tree_service.write_folder_files(owner_user_id, owner_id, folder["id"], files)
    await shared_skill_service.publish_folder(
        owner_user_id,
        owner_id,
        folder["id"],
        title=title,
        description=description,
        discoverable=True,
        source_github_url=source_url,
    )
    return "created"


async def _create_root_folder(owner_user_id: UUID, owner_id: UUID, title: str) -> dict:
    # Imports can share a title; folder names are unique per parent, so
    # suffix like fork_skill does.
    name = title
    for n in range(2, 50):
        try:
            return await files_tree_service.create_folder(
                owner_user_id=owner_user_id, name=name, created_by=owner_id
            )
        except files_tree_service.DuplicateFolderName:
            name = f"{title} ({n})"
    raise ValueError(f"Could not find a free folder name for {title!r}")


# ===== Whole-repo operations (script + admin dashboard) =====


async def user_github_token(user_id: UUID) -> str | None:
    """The user's GitHub connection token, or None when not connected.
    Auth is opportunistic here — public repos import without it."""
    try:
        return await integration_storage.get_valid_token(user_id, "github")
    except HTTPException:
        return None


async def import_repo_for_user(owner_user_id: UUID, user_id: UUID, repo_url: str) -> dict:
    """Copy a whole repo into the active scope (the user's own, or a workspace
    they belong to) as one new root folder — a straight copy preserving
    structure. Any folder containing a SKILL.md derives as a skill
    automatically (skill-ness is never stored). Private repos work when the
    user's GitHub connection can read them."""
    token = await user_github_token(user_id)
    repo_name, files = await fetch_repo_files(repo_url, token)
    if not files:
        raise ValueError("That repo has no importable files")
    folder = await _create_root_folder(owner_user_id, user_id, repo_name)
    await files_tree_service.write_folder_files(owner_user_id, user_id, folder["id"], files)
    return {"folder_id": str(folder["id"]), "name": folder["name"], "files": len(files)}


async def list_user_repos(user_id: UUID) -> list[dict]:
    """Repos the user's GitHub connection can access, most recently pushed
    first. Raises 401 when GitHub isn't connected."""
    token = await integration_storage.get_valid_token(user_id, "github")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_API}/user/repos",
            params={"per_page": 100, "sort": "pushed"},
            headers=_api_headers(token),
        )
        resp.raise_for_status()
        return [
            {
                "full_name": r["full_name"],
                "html_url": r["html_url"],
                "private": r["private"],
                "description": r["description"] or "",
            }
            for r in resp.json()
        ]


async def import_repo(repo_url: str) -> dict:
    """Import every SKILL.md folder in a repo into the curator scope.

    Returns a summary: how many skills the repo had and how many were newly
    created vs updated in place. Idempotent — re-running tracks upstream."""
    owner_user_id, owner_id = await ensure_curator()
    skills = await fetch_repo_skills(repo_url)
    created = updated = 0
    for skill in skills:
        result = await import_skill(
            owner_user_id,
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
        "SELECT folder_id FROM skills WHERE source_github_url = $1 OR source_github_url LIKE $2",
        base,
        f"{base}/tree/%",
    )
    for r in rows:
        await files_tree_service.clear_folder_contents(r["folder_id"])
        await pool.execute("DELETE FROM folders WHERE id = $1", r["folder_id"])
    return len(rows)
