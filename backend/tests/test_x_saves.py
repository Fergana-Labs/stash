"""Archived X (Twitter) saves and tweet fetching.

The X saves integration is retired: nothing syncs any more, but the saves it
archived stay readable. Tweet fetching survives for web clips of x.com status
URLs (tweet_fetch).
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services import source_service, tweet_fetch

from .conftest import unique_name

_THREAD_ROOT = {
    "id": "500",
    "text": "thread: why agents need memory 1/",
    "author": {"userName": "me"},
    "createdAt": "Wed Jul 01 12:00:00 +0000 2025",
    "conversationId": "500",
    "replyCount": 12,
}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeApi:
    """twitterapi.io tweet-by-id and thread-context lookups."""

    thread_tweets: list = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if url == tweet_fetch.TAPI_TWEETS_URL:
            assert params["tweet_ids"] == "500"
            return _FakeResponse({"tweets": [_THREAD_ROOT]})
        if url == tweet_fetch.TAPI_THREAD_URL:
            return _FakeResponse({"tweets": type(self).thread_tweets, "has_next_page": False})
        raise AssertionError(f"unexpected URL {url}")


@pytest.mark.asyncio
async def test_fetch_tweet_markdown_renders_the_whole_author_chain(monkeypatch) -> None:
    # Thread context mixes the author's continuation with a stranger's reply;
    # only the author's connected chain belongs in the clip.
    _FakeApi.thread_tweets = [
        {
            "id": "501",
            "text": "it compounds 2/",
            "author": {"userName": "me"},
            "createdAt": "Wed Jul 01 12:01:00 +0000 2025",
            "inReplyToId": "500",
        },
        {
            "id": "601",
            "text": "wrong take",
            "author": {"userName": "stranger"},
            "createdAt": "Wed Jul 01 12:02:00 +0000 2025",
            "inReplyToId": "500",
        },
        {
            "id": "502",
            "text": "ship it 3/",
            "author": {"userName": "me"},
            "createdAt": "Wed Jul 01 12:03:00 +0000 2025",
            "inReplyToId": "501",
        },
    ]
    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", "tapi-key")
    monkeypatch.setattr(tweet_fetch, "httpx", SimpleNamespace(AsyncClient=_FakeApi))

    tweet = await tweet_fetch.fetch_tweet_markdown("500")

    assert tweet["title"] == "@me - 2025-07-01"
    content = tweet["markdown"]
    assert content.startswith("thread: why agents need memory 1/")
    assert "## Thread by @me (3 posts)" in content
    assert content.index("it compounds 2/") < content.index("ship it 3/")
    assert "wrong take" not in content


@pytest.mark.asyncio
async def test_fetch_tweet_markdown_requires_the_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", None)
    with pytest.raises(RuntimeError, match="TWITTERAPI_IO_KEY"):
        await tweet_fetch.fetch_tweet_markdown("500")


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


async def _x_source(owner_id: str) -> dict:
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="x_saves",
        external_ref="me",
        display_name="X",
        settings={},
    )
    return await source_service.get_source_for_sync(UUID(source["id"]))


async def _insert_pending(pool, owner_id, source_id, path, kind):
    await pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref) "
        "VALUES ($1, $2, $3, $3, $4, $3)",
        UUID(owner_id),
        UUID(source_id),
        path,
        kind,
    )


async def _insert_done(pool, owner_id, source_id, path, content):
    await _insert_pending(pool, owner_id, source_id, path, "Bookmark")
    await pool.execute(
        "UPDATE x_save_docs SET content = $3, hydration_status = 'done' "
        "WHERE source_id = $1 AND path = $2",
        UUID(source_id),
        path,
        content,
    )


@pytest.mark.asyncio
async def test_bookmarks_list_newest_first_across_id_lengths(client, pool) -> None:
    """A bookmark list you can only read oldest-first buries the thing you
    saved five minutes ago; the listing must order by numeric tweet id (which
    grows over time), not lexicographic path — a 2010-era short id is old."""
    _, owner_id = await _register(client)
    source = await _x_source(owner_id)
    await _insert_done(pool, owner_id, source["id"], "Bookmarks/999", "old tweet")
    await _insert_done(pool, owner_id, source["id"], "Bookmarks/1815550001", "newer tweet")
    await _insert_done(pool, owner_id, source["id"], "Bookmarks/1815550002", "newest tweet")

    entries = await source_service.source_entries(
        UUID(owner_id), UUID(owner_id), str(source["id"]), prefix="Bookmarks"
    )
    assert [e["path"] for e in entries] == [
        "Bookmarks/1815550002",
        "Bookmarks/1815550001",
        "Bookmarks/999",
    ]

    # Keyset continuation: the cursor is the last path served; the next page
    # continues strictly older, in the same order.
    first = await source_service.source_entries(
        UUID(owner_id), UUID(owner_id), str(source["id"]), prefix="Bookmarks", limit=2
    )
    rest = await source_service.source_entries(
        UUID(owner_id),
        UUID(owner_id),
        str(source["id"]),
        prefix="Bookmarks",
        after=first[-1]["path"],
    )
    assert [e["path"] for e in rest] == ["Bookmarks/999"]


@pytest.mark.asyncio
async def test_unarchived_saves_read_as_human_sentences(client, pool) -> None:
    """A failed archive must never serve the raw exception text to the reader,
    and a pending one must say it's still archiving — while the listing marks
    both so they are distinguishable from healthy saves without opening them."""
    _, owner_id = await _register(client)
    source = await _x_source(owner_id)
    await _insert_pending(pool, owner_id, source["id"], "Bookmarks/2001", "Bookmark")
    await pool.execute(
        "UPDATE x_save_docs SET hydration_status = 'failed', "
        "hydration_error = 'RuntimeError: tweet 2001 is unavailable' "
        "WHERE source_id = $1 AND path = 'Bookmarks/2001'",
        UUID(source["id"]),
    )
    await _insert_pending(pool, owner_id, source["id"], "Bookmarks/2002", "Bookmark")

    ok, failed = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "Bookmarks/2001"
    )
    assert ok
    assert failed["http_status"] == 422
    assert "couldn't be archived" in failed["error"]
    assert "RuntimeError" not in failed["error"]

    ok, pending = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "Bookmarks/2002"
    )
    assert ok
    assert pending["http_status"] == 409
    assert "Still archiving" in pending["error"]

    entries = await source_service.source_entries(
        UUID(owner_id), UUID(owner_id), str(source["id"]), prefix="Bookmarks"
    )
    statuses = {e["path"]: e["status"] for e in entries}
    assert statuses["Bookmarks/2001"] == "failed"
    assert statuses["Bookmarks/2002"] == "pending"
