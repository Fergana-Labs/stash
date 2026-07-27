from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from backend.services import github_pr_service, linear_ticket_service
from backend.services.github_pr_service import GitHubPullRequest, PullRequestRef

from .conftest import unique_name


async def _register(client):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return response.json()["api_key"]


async def _scope(client, key):
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_extract_pull_request_refs_deduplicates_github_urls():
    refs = github_pr_service.extract_pull_request_refs(
        [
            "Opened https://github.com/Fergana-Labs/Stash/pull/381",
            "Review: https://github.com/fergana-labs/stash/pull/381/files",
            "Other: https://github.com/fergana-labs/stash/pull/382.",
        ]
    )

    assert refs == [
        PullRequestRef(owner="fergana-labs", repo="stash", number=381),
        PullRequestRef(owner="fergana-labs", repo="stash", number=382),
    ]


def test_labels_for_pull_request_reads_branch_title_body_and_commits():
    pr = GitHubPullRequest(
        ref=PullRequestRef(owner="fergana-labs", repo="stash", number=381),
        html_url="https://github.com/fergana-labs/stash/pull/381",
        title="FER-19 label sessions from pull requests",
        body="Connects https://linear.app/ferganalabs/issue/FER-20/link-from-prs",
        head_ref="henry/fer-21-pr-labels",
        commit_messages=("FER-22 add discovery service", "No ticket here"),
    )

    labels = {
        label.ticket_identifier: label for label in github_pr_service.labels_for_pull_request(pr)
    }

    assert labels["FER-19"].source == "github_pr_title"
    assert labels["FER-20"].source == "github_pr_body"
    assert labels["FER-20"].ticket_url == (
        "https://linear.app/ferganalabs/issue/FER-20/link-from-prs"
    )
    assert labels["FER-21"].source == "github_pr_branch"
    assert labels["FER-22"].source == "github_pr_commit"


@pytest.mark.asyncio
async def test_discover_session_labels_records_pr_and_upserts_ticket(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key = await _register(client)
    owner_user_id = await _scope(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    monkeypatch.setattr(github_pr_service, "enqueue_session_discovery", lambda _session_id: None)

    pushed = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "codex",
                    "event_type": "assistant_message",
                    "content": "Opened https://github.com/Fergana-Labs/stash/pull/381",
                    "session_id": "sess-pr-linear",
                }
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    session = await pool.fetchrow(
        "SELECT id FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        owner_user_id,
        "sess-pr-linear",
    )

    async def no_token(_user_id):
        return None

    async def fetch_pull_request(ref, access_token):
        assert access_token is None
        assert ref == PullRequestRef(owner="fergana-labs", repo="stash", number=381)
        return GitHubPullRequest(
            ref=ref,
            html_url="https://github.com/Fergana-Labs/stash/pull/381",
            title="FER-19 discover tickets through PRs",
            body="",
            head_ref="henry/pr-labels",
            commit_messages=(),
        )

    monkeypatch.setattr(github_pr_service, "_github_token_for_user", no_token)
    monkeypatch.setattr(github_pr_service, "fetch_pull_request", fetch_pull_request)
    monkeypatch.setattr(linear_ticket_service, "enqueue_session_enrichment", lambda *_args: None)

    count = await github_pr_service.discover_session_labels(session["id"])

    assert count == 1
    pr_row = await pool.fetchrow(
        "SELECT owner, repo, pull_number, pull_title, head_ref "
        "FROM session_github_pull_requests WHERE session_row_id = $1",
        session["id"],
    )
    assert dict(pr_row) == {
        "owner": "fergana-labs",
        "repo": "stash",
        "pull_number": 381,
        "pull_title": "FER-19 discover tickets through PRs",
        "head_ref": "henry/pr-labels",
    }

    label = await pool.fetchrow(
        "SELECT ticket_identifier, source, confidence "
        "FROM session_linear_tickets WHERE session_row_id = $1",
        session["id"],
    )
    assert label["ticket_identifier"] == "FER-19"
    assert label["source"] == "github_pr_title"
    assert label["confidence"] == pytest.approx(0.9)


class _FakeGitHubResponse:
    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeGitHubClient:
    responses: dict = {}

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        return type(self).responses[url]


async def test_fetch_pull_request_returns_none_when_token_cannot_read(monkeypatch):
    # A 403 on someone else's private repo is permanent for this token; None
    # records the check so the reconciler stops re-enqueueing the session
    # every 5 minutes forever.
    ref = PullRequestRef(owner="acme", repo="private", number=7)
    _FakeGitHubClient.responses = {
        "https://api.github.com/repos/acme/private/pulls/7": _FakeGitHubResponse(status_code=403)
    }
    monkeypatch.setattr(github_pr_service, "httpx", SimpleNamespace(AsyncClient=_FakeGitHubClient))

    assert await github_pr_service.fetch_pull_request(ref, "token") is None


async def test_fetch_pull_request_raises_on_rate_limit(monkeypatch):
    # Rate limiting also arrives as 403 but is transient — it must raise so
    # the reconciler retries later instead of permanently recording the check.
    ref = PullRequestRef(owner="acme", repo="busy", number=8)
    _FakeGitHubClient.responses = {
        "https://api.github.com/repos/acme/busy/pulls/8": _FakeGitHubResponse(
            status_code=403, headers={"x-ratelimit-remaining": "0"}
        )
    }
    monkeypatch.setattr(github_pr_service, "httpx", SimpleNamespace(AsyncClient=_FakeGitHubClient))

    with pytest.raises(RuntimeError):
        await github_pr_service.fetch_pull_request(ref, "token")
