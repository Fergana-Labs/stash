"""Import public GitHub skill repos into the Discover catalog.

Each repo is scanned for folders containing a SKILL.md; every match becomes
a published + discoverable skill in the "Stash Curated" workspace, attributed
back to GitHub via source_github_url. Re-running updates existing imports in
place (matched by source_github_url), so the catalog tracks upstream.

Usage:
    python scripts/import_github_skills.py [REPO_URL ...]
        [--repos-file scripts/discover_skill_repos.txt] [--dry-run]

Env:
    GITHUB_TOKEN  optional; raises the GitHub API rate limit 60 -> 5000/hr.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")

sys.path.insert(0, str(REPO_ROOT))

from backend import database  # noqa: E402
from backend.services import github_skill_import  # noqa: E402

DEFAULT_REPOS_FILE = REPO_ROOT / "scripts" / "discover_skill_repos.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("import_github_skills")


def _reenable_logging() -> None:
    """database.init_db() runs alembic, whose fileConfig disables existing
    loggers and caps root at WARNING — undo that for the import loggers."""
    for lg in (log, logging.getLogger(github_skill_import.__name__)):
        lg.disabled = False
        lg.setLevel(logging.INFO)
        lg.propagate = False
        if not lg.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            lg.addHandler(handler)


def read_repos_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="*", help="GitHub repo URLs (override the repos file)")
    parser.add_argument("--repos-file", type=Path, default=DEFAULT_REPOS_FILE)
    parser.add_argument("--dry-run", action="store_true", help="list skills without importing")
    args = parser.parse_args()

    repo_urls = args.repos or read_repos_file(args.repos_file)
    if not repo_urls:
        parser.error(f"no repos given and {args.repos_file} is empty")

    await database.init_db()
    _reenable_logging()
    workspace_id, owner_id = await github_skill_import.ensure_curator()
    created = updated = failed = 0
    for repo_url in repo_urls:
        try:
            skills = await github_skill_import.fetch_repo_skills(repo_url)
        except Exception:
            log.exception("failed to fetch %s", repo_url)
            failed += 1
            continue
        if not skills:
            log.warning("%s: no SKILL.md folders found", repo_url)
            continue
        for skill in skills:
            if args.dry_run:
                log.info(
                    "[dry-run] %s (%d files) <- %s",
                    skill["fallback_title"],
                    len(skill["files"]),
                    skill["source_url"],
                )
                continue
            try:
                result = await github_skill_import.import_skill(
                    workspace_id,
                    owner_id,
                    source_url=skill["source_url"],
                    fallback_title=skill["fallback_title"],
                    files=skill["files"],
                )
            except Exception:
                log.exception("failed to import %s", skill["source_url"])
                failed += 1
                continue
            log.info("%s: %s", result, skill["source_url"])
            created += result == "created"
            updated += result == "updated"
    log.info("done: %d created, %d updated, %d failed", created, updated, failed)
    await database.close_db()


if __name__ == "__main__":
    asyncio.run(main())
