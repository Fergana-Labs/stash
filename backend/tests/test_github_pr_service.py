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


async def _workspace(client, key):
    response = await client.post(
        "/api/v1/workspaces",
        json={"name": "ws-" + unique_name()},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 201
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
        label.ticket_identifier: label
        for label in github_pr_service.labels_for_pull_request(pr)
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
    workspace_id = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    monkeypatch.setattr(github_pr_service, "enqueue_session_discovery", lambda _session_id: None)

    pushed = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions/events/batch",
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
        "SELECT id FROM sessions WHERE workspace_id = $1 AND session_id = $2",
        workspace_id,
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
