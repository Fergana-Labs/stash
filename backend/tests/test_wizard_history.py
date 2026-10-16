import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.services import session_service
from backend.services.intuition import history, service
from backend.services.rm import traces
from backend.services.rm.adapters import CanonicalStep, CanonicalTrace

from .conftest import unique_name


async def account(client):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("history"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


async def recorded(pool, owner, text="Please improve this website", n=3):
    sid = str(uuid4())
    session = await session_service.upsert_session(owner, sid, agent_name="codex", created_by=owner)
    now = datetime.now(UTC)
    for index in range(n):
        await pool.execute(
            """INSERT INTO history_events(owner_user_id,created_by,agent_name,event_type,content,session_id,created_at)
             VALUES($1,$1,'codex',$2,$3,$4,$5)""",
            owner,
            "user_message" if index % 2 == 0 else "assistant_message",
            f"{text} {index}",
            sid,
            now + timedelta(seconds=index),
        )
    return session


async def test_search_and_read_existing_history_are_owner_scoped(client, pool):
    owner, stranger = await account(client), await account(client)
    mine = await recorded(pool, owner)
    other = await recorded(pool, stranger)
    deleted = await recorded(pool, owner)
    await session_service.delete_session(deleted["id"], owner, owner)
    found = await history.search(owner, query="website", agent="codex", source="recorded")
    assert [row["id"] for row in found["results"]] == [str(mine["id"])]
    page = await history.read(owner, kind="session", id=str(mine["id"]), offset=1, limit=1)
    assert page["total"] == 3 and page["has_more"] and page["next_offset"] == 2
    assert page["events"][0]["role"] == "assistant"
    for id in (other["id"], deleted["id"]):
        with pytest.raises(service.NotFound):
            await history.read(owner, kind="session", id=str(id))


async def test_history_examples_keep_real_content_provenance_and_require_review(client, pool):
    owner = await account(client)
    session = await recorded(pool, owner)
    detail = await service.create_model(
        owner,
        name="Website taste",
        output_type="choice",
        description="Would I ship it?",
        labels=[{"id": "good", "description": "Ship"}, {"id": "bad", "description": "Redesign"}],
        rubric=[],
    )
    mid = detail["model"]["id"]
    selection = {
        "kind": "session",
        "id": str(session["id"]),
        "offset": 0,
        "limit": 3,
        "label": "bad",
        "note": "Check whether the requested change was made",
    }
    created = await history.add_examples(owner, mid, [selection])
    assert len(created) == 1
    example = created[0]
    assert (
        example["needs_review"] and example["label"] == "bad" and example["source"] == "production"
    )
    assert example["item"]["source"]["session_id"] == session["session_id"]
    assert example["item"]["events"][0]["content"] == "Please improve this website 0"
    assert await history.add_examples(owner, mid, [selection]) == []
    assert len(await service.list_examples(owner, mid)) == 1


async def test_reading_large_history_is_explicitly_partial(client, pool):
    owner = await account(client)
    session = await recorded(pool, owner, text="x" * 12000, n=10)
    page = await history.read(owner, kind="session", id=str(session["id"]), limit=10)
    assert page["content_truncated"] and page["has_more"]
    assert page["total"] == 10 and len(json.dumps(page)) < 10000
    assert 0 < page["next_offset"] < 10


async def test_trace_fallback_excludes_private_setup_reasoning_other_owners_and_deleted_sessions(
    client, pool
):
    owner, other = await account(client), await account(client)
    async with pool.acquire() as conn:
        tid = (
            await traces.store_traces(
                conn,
                owner,
                "stash",
                [
                    CanonicalTrace(
                        "standalone",
                        "Website revision",
                        {"agent": "codex"},
                        [
                            CanonicalStep("system", "PRIVATE_SETUP"),
                            CanonicalStep(
                                "assistant", "PRIVATE_REASONING", metadata={"thinking": True}
                            ),
                            CanonicalStep("user", "Please change the website"),
                            CanonicalStep(
                                "assistant",
                                "Changed the button corners",
                                metadata={"label": {"verdict": "bad"}, "reward": {"score": 1}},
                            ),
                        ],
                    )
                ],
            )
        )[0]
    found = await history.search(owner, query="website", source="recorded")
    assert len(found["results"]) == 1 and found["results"][0]["match_offset"] == 0
    page = await history.read(owner, kind="trace", id=str(tid))
    assert page["total"] == 2 and page["events"][0]["role"] == "user"
    assert not any(word in json.dumps(page["events"]) for word in ("PRIVATE", "verdict", "reward"))
    with pytest.raises(service.NotFound):
        await history.read(other, kind="trace", id=str(tid))
    old = await recorded(pool, owner)
    async with pool.acquire() as conn:
        shadow = (
            await traces.store_traces(
                conn,
                owner,
                "stash",
                [
                    CanonicalTrace(
                        old["session_id"],
                        "Website old session",
                        {},
                        [CanonicalStep("user", "Website")],
                    )
                ],
            )
        )[0]
    await session_service.delete_session(old["id"], owner, owner)
    found = await history.search(owner, query="website", source="recorded")
    assert [r["id"] for r in found["results"]] == [str(tid)]
    with pytest.raises(service.NotFound):
        await history.read(owner, kind="trace", id=str(shadow))
