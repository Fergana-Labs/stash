"""Discover Linear ticket labels through GitHub pull request links."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

import httpx

from ..database import get_pool
from ..integrations import storage as integration_storage
from . import linear_ticket_service

GITHUB_API_URL = "https://api.github.com"
MAX_PULL_REQUESTS_PER_SESSION = 10
MAX_COMMIT_MESSAGES = 100

_PULL_REQUEST_URL = re.compile(
    r"https?://github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/"
    r"pull/(?P<number>\d+)",
    re.IGNORECASE,
)
_SQL_PULL_REQUEST_URL = r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[0-9]+"


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.number}"


@dataclass(frozen=True)
class GitHubPullRequest:
    ref: PullRequestRef
    html_url: str
    title: str
    body: str
    head_ref: str
    commit_messages: tuple[str, ...]


def extract_pull_request_refs(contents: list[str]) -> list[PullRequestRef]:
    refs: dict[tuple[str, str, int], PullRequestRef] = {}
    for content in contents:
        for match in _PULL_REQUEST_URL.finditer(content):
            ref = PullRequestRef(
                owner=match.group("owner").lower(),
                repo=match.group("repo").lower(),
                number=int(match.group("number")),
            )
            refs[(ref.owner, ref.repo, ref.number)] = ref
    return list(refs.values())


def has_pull_request_hint(contents: list[str]) -> bool:
    return bool(extract_pull_request_refs(contents))


def labels_for_pull_request(pr: GitHubPullRequest) -> list[linear_ticket_service.LinearTicketLabel]:
    sources: list[tuple[str, str, float]] = [
        (pr.head_ref, "github_pr_branch", 0.92),
        (pr.title, "github_pr_title", 0.9),
        (pr.body, "github_pr_body", 0.85),
    ]
    sources.extend(
        (message, "github_pr_commit", 0.8) for message in pr.commit_messages[:MAX_COMMIT_MESSAGES]
    )
    return linear_ticket_service.extract_ticket_mentions(sources)


def enqueue_session_discovery(session_row_id: UUID) -> None:
    from ..tasks.linear_tickets import discover_session_github_prs

    discover_session_github_prs.delay(str(session_row_id))


async def discover_session_labels(session_row_id: UUID) -> int:
    pool = get_pool()
    session = await pool.fetchrow(
        """
        SELECT owner_user_id, session_id, created_by
        FROM sessions
        WHERE id = $1 AND deleted_at IS NULL
        """,
        session_row_id,
    )
    if not session:
        return 0

    rows = await pool.fetch(
        """
        SELECT content
        FROM history_events
        WHERE owner_user_id = $1 AND session_id = $2
        ORDER BY created_at, id
        """,
        session["owner_user_id"],
        session["session_id"],
    )
    refs = extract_pull_request_refs([row["content"] for row in rows])[
        :MAX_PULL_REQUESTS_PER_SESSION
    ]
    if not refs:
        return 0

    token = await _github_token_for_user(session["created_by"])
    labels: list[linear_ticket_service.LinearTicketLabel] = []
    for ref in refs:
        pr = await fetch_pull_request(ref, token)
        if pr is None:
            await _record_pull_request_check(pool, session["owner_user_id"], session_row_id, ref)
            continue

        await _record_pull_request(pool, session["owner_user_id"], session_row_id, pr)
        labels.extend(labels_for_pull_request(pr))

    await linear_ticket_service.upsert_session_labels(
        session["owner_user_id"],
        session_row_id,
        labels,
    )
    if labels:
        linear_ticket_service.enqueue_session_enrichment(session["owner_user_id"], session_row_id)
    return len(labels)


async def discover_unprocessed_sessions(limit: int) -> int:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT s.id
        FROM sessions s
        WHERE s.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1
            FROM session_github_pull_requests sgpr
            WHERE sgpr.session_row_id = s.id
          )
          AND EXISTS (
            SELECT 1
            FROM history_events he
            WHERE he.owner_user_id = s.owner_user_id
              AND he.session_id = s.session_id
              AND he.content ~* $2
          )
        ORDER BY s.started_at DESC
        LIMIT $1
        """,
        limit,
        _SQL_PULL_REQUEST_URL,
    )
    for row in rows:
        enqueue_session_discovery(row["id"])
    return len(rows)


async def fetch_pull_request(
    ref: PullRequestRef,
    access_token: str | None,
) -> GitHubPullRequest | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stash-linear-ticket-discovery",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    base_url = f"{GITHUB_API_URL}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        response = await client.get(base_url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()

        commits_response = await client.get(f"{base_url}/commits", params={"per_page": 100})
        commits_response.raise_for_status()
        commits_payload = commits_response.json()

    commit_messages = tuple(
        commit["commit"]["message"]
        for commit in commits_payload
        if commit.get("commit", {}).get("message")
    )
    return GitHubPullRequest(
        ref=ref,
        html_url=payload["html_url"],
        title=payload.get("title") or "",
        body=payload.get("body") or "",
        head_ref=(payload.get("head") or {}).get("ref") or "",
        commit_messages=commit_messages,
    )


async def _github_token_for_user(user_id: UUID | None) -> str | None:
    if user_id is None:
        return None

    try:
        return await integration_storage.get_valid_token(user_id, "github")
    except Exception:
        # GitHub auth is opportunistic: public PR metadata still works without it.
        return None


async def _record_pull_request(
    pool,
    owner_user_id: UUID,
    session_row_id: UUID,
    pr: GitHubPullRequest,
) -> None:
    await pool.execute(
        """
        INSERT INTO session_github_pull_requests (
          owner_user_id,
          session_row_id,
          owner,
          repo,
          pull_number,
          pull_url,
          pull_title,
          head_ref,
          fetched_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (session_row_id, owner, repo, pull_number) DO UPDATE SET
          pull_url = EXCLUDED.pull_url,
          pull_title = EXCLUDED.pull_title,
          head_ref = EXCLUDED.head_ref,
          fetched_at = now(),
          updated_at = now()
        """,
        owner_user_id,
        session_row_id,
        pr.ref.owner,
        pr.ref.repo,
        pr.ref.number,
        pr.html_url,
        pr.title or None,
        pr.head_ref or None,
    )


async def _record_pull_request_check(
    pool,
    owner_user_id: UUID,
    session_row_id: UUID,
    ref: PullRequestRef,
) -> None:
    await pool.execute(
        """
        INSERT INTO session_github_pull_requests (
          owner_user_id,
          session_row_id,
          owner,
          repo,
          pull_number,
          pull_url,
          fetched_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (session_row_id, owner, repo, pull_number) DO UPDATE SET
          fetched_at = now(),
          updated_at = now()
        """,
        owner_user_id,
        session_row_id,
        ref.owner,
        ref.repo,
        ref.number,
        ref.url,
    )
