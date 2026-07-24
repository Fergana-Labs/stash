from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.services import linear_api_service, linear_ticket_service
from backend.services.linear_api_service import LinearComment, LinearIssue


@pytest.mark.asyncio
async def test_fetch_issue_parses_linear_graphql_response(monkeypatch):
    async def graphql(query, variables, access_token):
        assert variables == {"id": "FER-19"}
        assert access_token == "test-token"
        return {
            "data": {
                "issue": {
                    "id": "issue-id",
                    "identifier": "FER-19",
                    "title": "Customize Stash homepage cover",
                    "url": "https://linear.app/ferganalabs/issue/FER-19/customize",
                    "updatedAt": "2026-05-19T21:45:50.344Z",
                    "state": {"name": "Done"},
                    "assignee": {"name": "Henry Dowling"},
                    "team": {"key": "FER", "name": "Ferganalabs"},
                    "project": {"name": "symphony"},
                    "comments": {
                        "nodes": [
                            {"body": "shipped in v2", "user": {"name": "Grace Hopper"}},
                        ]
                    },
                }
            }
        }

    monkeypatch.setattr(linear_api_service, "_graphql", graphql)

    issue = await linear_api_service.fetch_issue("FER-19", "test-token")

    assert issue == LinearIssue(
        issue_id="issue-id",
        identifier="FER-19",
        title="Customize Stash homepage cover",
        url="https://linear.app/ferganalabs/issue/FER-19/customize",
        status="Done",
        assignee_name="Henry Dowling",
        team_key="FER",
        team_name="Ferganalabs",
        project_name="symphony",
        updated_at=datetime(2026, 5, 19, 21, 45, 50, 344000, tzinfo=UTC),
        comments=(LinearComment(author_name="Grace Hopper", body="shipped in v2"),),
    )


@pytest.mark.asyncio
async def test_enrich_session_labels_updates_canonical_linear_fields(monkeypatch):
    session_row_id = UUID("00000000-0000-0000-0000-000000000019")
    OWNER_USER_ID = UUID("00000000-0000-0000-0000-0000000000aa")
    updated_at = datetime(2026, 5, 19, 21, 45, 50, tzinfo=UTC)

    class Pool:
        def __init__(self):
            self.executed = []

        async def fetch(self, *args):
            return [{"ticket_identifier": "FER-19", "owner_user_id": OWNER_USER_ID}]

        async def execute(self, *args):
            self.executed.append(args)

    pool = Pool()

    async def fetch_issue(identifier, access_token):
        assert identifier == "FER-19"
        assert access_token == "test-token"
        return LinearIssue(
            issue_id="issue-id",
            identifier="FER-19",
            title="Customize Stash homepage cover",
            url="https://linear.app/ferganalabs/issue/FER-19/customize",
            status="Done",
            assignee_name="Henry Dowling",
            team_key="FER",
            team_name="Ferganalabs",
            project_name="symphony",
            updated_at=updated_at,
        )

    async def owner_token(owner_user_id):
        assert owner_user_id == OWNER_USER_ID
        return "test-token"

    monkeypatch.setattr(linear_ticket_service, "get_pool", lambda: pool)
    monkeypatch.setattr(linear_ticket_service, "_owner_linear_token", owner_token)
    monkeypatch.setattr(linear_ticket_service.linear_api_service, "fetch_issue", fetch_issue)

    updated = await linear_ticket_service.enrich_session_labels(session_row_id)

    assert updated == 1
    [execute_args] = pool.executed
    assert execute_args[1:] == (
        session_row_id,
        "issue-id",
        "Customize Stash homepage cover",
        "https://linear.app/ferganalabs/issue/FER-19/customize",
        "Done",
        "Henry Dowling",
        "FER",
        "Ferganalabs",
        "symphony",
        updated_at,
        "FER-19",
    )
