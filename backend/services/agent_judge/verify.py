"""Read-only checks against sources of truth, for claims a transcript alone cannot settle.

"I opened PR #1247 and the tests pass" is a claim about GitHub, not about the
transcript. When the owner has GitHub connected, a worker can look the PR up:
whether it exists, which files it changed, and what CI concluded. Nothing here
writes anywhere. When a source is not connected the answer says so, and the
claim stays unverifiable rather than guessed.
"""

from __future__ import annotations

from uuid import UUID

import httpx

API = "https://api.github.com"
TIMEOUT = 15.0


class Unavailable(Exception):
    """The source of truth cannot be reached for this owner."""


async def _token(owner_id: UUID | None) -> str:
    if owner_id is None:
        raise Unavailable("No owner to look up connections for")
    from ...integrations.storage import get_valid_token

    try:
        return await get_valid_token(owner_id, "github")
    except Exception as exc:  # Not connected, revoked, or refresh failed: all mean "cannot check".
        raise Unavailable("GitHub is not connected for this account") from exc


async def github_pr(owner_id: UUID | None, repo: str, number: int) -> str:
    """PR state, changed files and CI conclusion, as text a worker can cite."""
    try:
        token = await _token(owner_id)
    except Unavailable as exc:
        return f"UNAVAILABLE: {exc}. Treat claims about this PR as unverifiable."
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        pr = await client.get(f"{API}/repos/{repo}/pulls/{number}")
        if pr.status_code == 404:
            return f"NOT FOUND: {repo}#{number} does not exist or is not visible to this account."
        if pr.status_code != 200:
            return f"UNAVAILABLE: GitHub returned {pr.status_code}."
        data = pr.json()
        files = await client.get(
            f"{API}/repos/{repo}/pulls/{number}/files", params={"per_page": 100}
        )
        checks = await client.get(
            f"{API}/repos/{repo}/commits/{data['head']['sha']}/check-runs", params={"per_page": 100}
        )
    changed = [f["filename"] for f in files.json()] if files.status_code == 200 else []
    runs = checks.json().get("check_runs", []) if checks.status_code == 200 else []
    conclusions = [f"{r['name']}: {r.get('conclusion') or r.get('status')}" for r in runs]
    failing = [
        r["name"] for r in runs if r.get("conclusion") in ("failure", "timed_out", "cancelled")
    ]
    lines = [
        f"PR {repo}#{number}: “{data['title']}” by {data['user']['login']}",
        f"STATE: {data['state']}{' (merged)' if data.get('merged') else ''}, created {data['created_at']}",
        f"FILES CHANGED ({len(changed)}): " + ", ".join(changed[:40]),
        "CHECKS: " + ("; ".join(conclusions[:30]) if conclusions else "none reported"),
        f"FAILING CHECKS: {', '.join(failing) if failing else 'none'}",
    ]
    return "\n".join(lines)
