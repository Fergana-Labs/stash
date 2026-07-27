"""URL imports: async fetch jobs behind the clip API.

The router must classify URLs in one place (YouTube → transcript, arXiv
abs → paper PDF, PDFs → file clips, HTML → article pages), and every row
must end as either a hydrated clip or a link-only bookmark — a dead link
in a bookmark import can never block the batch or silently vanish. Rate
limits park rows instead of burning attempts, and login walls hand rows
to the extension (needs_client) before giving up.
"""

from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services import clip_router, storage_service, url_import_service, youtube_transcript
from backend.services.youtube_transcript import TranscriptUnavailable
from backend.tasks import clips as clips_tasks
from backend.tasks import extraction

from .conftest import unique_name
from .test_clips import ARTICLE_HTML


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


# --- URL classification ---


def test_youtube_special_page_matches_watch_shorts_and_short_links() -> None:
    yt = clip_router.YouTubeTranscriptPage()
    assert yt.matches("https://www.youtube.com/watch?v=abc123")
    assert yt.matches("https://youtube.com/shorts/abc123")
    assert yt.matches("https://youtu.be/abc123")
    assert not yt.matches("https://youtu.be/")
    assert not yt.matches("https://www.youtube.com/@somechannel")
    assert not yt.matches("https://example.com/watch?v=abc123")


def test_x_special_page_matches_status_urls_only() -> None:
    x = clip_router.XThreadPage()
    assert x.matches("https://x.com/someone/status/1808168603721650680")
    assert x.matches("https://twitter.com/someone/statuses/9001?s=20")
    assert x.matches("https://x.com/i/status/9001")
    assert not x.matches("https://x.com/someone")
    assert not x.matches("https://example.com/someone/status/9001")


def test_arxiv_special_page_matches_abs_urls() -> None:
    arxiv = clip_router.ArxivPdfPage()
    assert arxiv.matches("https://arxiv.org/abs/2401.00001")
    assert arxiv.matches("https://www.arxiv.org/abs/2401.00001v2")
    assert not arxiv.matches("https://example.com/abs/x")


def test_is_special_page_covers_youtube_x_and_arxiv() -> None:
    assert clip_router.is_special_page("https://www.youtube.com/watch?v=abc")
    assert clip_router.is_special_page("https://arxiv.org/abs/2401.00001")
    assert clip_router.is_special_page("https://x.com/someone/status/9001")
    assert not clip_router.is_special_page("https://example.com/post")


# --- YouTube transcript fetching (ScrapeCreators + oEmbed) ---


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", youtube_transcript.SC_TRANSCRIPT_URL)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


class _FakeAsyncClient:
    """Feeds canned responses in call order (oEmbed first, then SC)."""

    def __init__(self, responses: list[_FakeResponse]):
        self._responses = responses
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        self.calls.append(url)
        return self._responses.pop(0)


def _fake_youtube_http(monkeypatch, responses: list[_FakeResponse]) -> _FakeAsyncClient:
    fake = _FakeAsyncClient(responses)
    monkeypatch.setattr(youtube_transcript.httpx, "AsyncClient", lambda **kw: fake)
    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", "test-key")
    return fake


@pytest.mark.asyncio
async def test_fetch_transcript_combines_oembed_and_scrapecreators(monkeypatch) -> None:
    _fake_youtube_http(
        monkeypatch,
        [
            _FakeResponse(200, {"title": "A Talk", "author_name": "Chan"}),
            _FakeResponse(200, {"transcript_only_text": "words words"}),
        ],
    )
    video = await youtube_transcript.fetch_transcript("https://www.youtube.com/watch?v=abc")
    assert video == {"title": "A Talk", "channel": "Chan", "transcript": "words words"}


@pytest.mark.asyncio
async def test_fetch_transcript_private_video_spends_no_credit(monkeypatch) -> None:
    fake = _fake_youtube_http(monkeypatch, [_FakeResponse(401)])
    with pytest.raises(TranscriptUnavailable, match="private or deleted"):
        await youtube_transcript.fetch_transcript("https://www.youtube.com/watch?v=abc")
    # oEmbed failing must short-circuit before the ScrapeCreators call.
    assert fake.calls == [youtube_transcript.OEMBED_URL]


@pytest.mark.asyncio
async def test_fetch_transcript_null_transcript_is_unavailable(monkeypatch) -> None:
    _fake_youtube_http(
        monkeypatch,
        [
            _FakeResponse(200, {"title": "A Talk", "author_name": "Chan"}),
            _FakeResponse(200, {"transcript_only_text": None}),
        ],
    )
    with pytest.raises(TranscriptUnavailable, match="No transcript"):
        await youtube_transcript.fetch_transcript("https://www.youtube.com/watch?v=abc")


@pytest.mark.asyncio
async def test_fetch_transcript_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", "")
    with pytest.raises(RuntimeError, match="SCRAPECREATORS_API_KEY"):
        await youtube_transcript.fetch_transcript("https://www.youtube.com/watch?v=abc")


# --- Endpoint behaviour ---


@pytest.mark.asyncio
async def test_clip_page_defers_youtube_to_worker(client: AsyncClient, pool, monkeypatch) -> None:
    dispatched: list[list[str]] = []
    monkeypatch.setattr(
        clips_tasks.process_url_imports, "delay", lambda ids: dispatched.append(ids)
    )
    headers, _ = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://www.youtube.com/watch?v=abc123", "html": "<html></html>"},
        headers=headers,
    )
    assert resp.status_code == 202
    import_id = resp.json()["import_id"]
    assert dispatched == [[import_id]]

    status = await client.get(f"/api/v1/me/clips/{import_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_clip_import_status_is_owner_scoped(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://youtu.be/abc123", "html": "<html></html>"},
        headers=headers,
    )
    import_id = resp.json()["import_id"]

    other = await client.get(f"/api/v1/me/clips/{import_id}", headers=other_headers)
    assert other.status_code == 404


# --- Worker processing ---


async def _make_import(owner_id: str, url: str, title: str | None = None) -> UUID:
    ids = await url_import_service.create_url_imports(
        owner_user_id=UUID(owner_id),
        created_by=UUID(owner_id),
        items=[{"url": url, "title": title}],
    )
    return ids[0]


@pytest.mark.asyncio
async def test_worker_turns_html_url_into_clip_page(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/post")

    async def fake_fetch(url: str):
        return ARTICLE_HTML.encode(), "text/html; charset=utf-8"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    page = await pool.fetchrow(
        "SELECT p.name, f.name AS folder_name FROM pages p "
        "JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        row["result_page_id"],
    )
    assert page["name"] == "Why Simplicity Wins"
    assert page["folder_name"] == "raw"


@pytest.mark.asyncio
async def test_worker_turns_pdf_url_into_file_clip(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://arxiv.org/abs/2401.00001")

    fetched: list[str] = []

    async def fake_fetch(url: str):
        fetched.append(url)
        return b"%PDF-1.4 fake body", "application/pdf"

    async def _upload(*args, **kwargs):
        return "test/key"

    async def _url(key):
        return f"https://blob.example/{key}"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)

    await clips_tasks._process_batch([import_id])

    assert fetched == ["https://arxiv.org/pdf/2401.00001"]
    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    file_row = await pool.fetchrow(
        "SELECT name, source_url FROM files WHERE id = $1", row["result_file_id"]
    )
    assert file_row["source_url"] == "https://arxiv.org/abs/2401.00001"
    assert file_row["name"].endswith(".pdf")


@pytest.mark.asyncio
async def test_worker_turns_youtube_url_into_transcript_page(
    client: AsyncClient, pool, monkeypatch
) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://www.youtube.com/watch?v=abc123")

    async def fake_transcript(url: str) -> dict:
        return {"title": "A Great Talk", "channel": "Chan", "transcript": "words words"}

    monkeypatch.setattr(clip_router.youtube_transcript, "fetch_transcript", fake_transcript)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    page = await pool.fetchrow(
        "SELECT p.name, p.content_markdown, f.name AS folder_name FROM pages p "
        "JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        row["result_page_id"],
    )
    assert page["name"] == "A Great Talk"
    assert page["folder_name"] == "raw"
    assert "words words" in page["content_markdown"]


@pytest.mark.asyncio
async def test_worker_turns_x_status_url_into_tweet_page(
    client: AsyncClient, pool, monkeypatch
) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://x.com/someone/status/9001")

    async def fake_tweet(tweet_id: str) -> dict:
        assert tweet_id == "9001"
        return {"title": "@someone - 2026-07-01", "markdown": "a banger\n\n— @someone"}

    monkeypatch.setattr(clip_router.x_indexer, "fetch_tweet_markdown", fake_tweet)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    page = await pool.fetchrow(
        "SELECT name, content_markdown FROM pages WHERE id = $1", row["result_page_id"]
    )
    assert page["name"] == "@someone - 2026-07-01"
    assert "a banger" in page["content_markdown"]


SHELL_HTML = "<html><body><div id='root'></div></body></html>"


@pytest.mark.asyncio
async def test_js_shell_pages_are_rescued_by_chromium_render(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """SPAs serve an empty shell over HTTP; the worker must escalate to a
    Chromium render and extract from the settled DOM instead of giving up."""
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://spa.example/post")
    rendered: list[str] = []

    async def fake_fetch(url: str):
        return SHELL_HTML.encode(), "text/html"

    async def fake_render(url: str) -> str:
        rendered.append(url)
        return ARTICLE_HTML

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    monkeypatch.setattr(clip_router.page_render_service, "render_page", fake_render)
    await clips_tasks._process_batch([import_id])

    assert rendered == ["https://spa.example/post"]
    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert row["error"] is None
    page = await pool.fetchrow("SELECT name FROM pages WHERE id = $1", row["result_page_id"])
    assert page["name"] == "Why Simplicity Wins"


@pytest.mark.asyncio
async def test_render_that_still_has_no_article_goes_link_only(
    client: AsyncClient, pool, monkeypatch
) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://spa.example/app", title="An App")

    async def fake_fetch(url: str):
        return SHELL_HTML.encode(), "text/html"

    async def fake_render(url: str) -> str:
        return SHELL_HTML

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    monkeypatch.setattr(clip_router.page_render_service, "render_page", fake_render)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert "ArticleExtractionError" in row["error"]
    assert row["result_page_id"] is None
    bookmarks = await _bookmark_rows(pool, owner_id)
    assert "An App" in bookmarks[0].values()


@pytest.mark.asyncio
async def test_worker_records_fetch_failure_on_row(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/dead-link")

    async def fake_fetch(url: str):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "failed"
    assert "ConnectError" in row["error"]
    assert row["attempts"] == 1


@pytest.mark.asyncio
async def test_done_rows_are_not_reclaimed(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/post")

    async def fake_fetch(url: str):
        return ARTICLE_HTML.encode(), "text/html"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])
    assert await url_import_service.claim(import_id) is None


async def _bookmark_rows(pool, owner_id: str) -> list[dict]:
    rows = await pool.fetch(
        "SELECT r.data FROM table_rows r JOIN tables t ON t.id = r.table_id "
        "WHERE t.name = 'Bookmarks' AND t.owner_user_id = $1",
        UUID(owner_id),
    )
    return [r["data"] for r in rows]


@pytest.mark.asyncio
async def test_unsupported_content_becomes_link_only(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """Content we can't capture is deterministic — the bookmark must still be
    saved as a link row instead of retrying or vanishing."""
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/video.mp4", title="A Video")

    async def fake_fetch(url: str):
        return b"\x00\x01binary", "video/mp4"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert "video/mp4" in row["error"]
    assert row["result_page_id"] is None

    bookmarks = await _bookmark_rows(pool, owner_id)
    assert len(bookmarks) == 1
    assert "A Video" in bookmarks[0].values()
    assert "Link" in bookmarks[0].values()


# --- Failure routing: rate limits, login walls, exhausted retries ---


def _status_error(code: int, url: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"HTTP {code}", request=request, response=httpx.Response(code, request=request)
    )


@pytest.mark.asyncio
async def test_429_parks_row_then_escalates_to_client(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """A rate limit parks the row for a spaced-out retry; a site that 429s
    every retry is blocking us, so the row escalates to needs_client instead
    of cycling forever."""
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/busy")

    async def fake_fetch(url: str):
        raise _status_error(429, url)

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["retry_at"] is not None
    # Parked rows are not claimable until the retry window passes.
    assert await url_import_service.claim(import_id) is None

    # Two more 429s across elapsed retry windows exhaust the attempts and
    # hand the row to the extension.
    for _ in range(2):
        await pool.execute("UPDATE url_imports SET retry_at = now() WHERE id = $1", import_id)
        await clips_tasks._process_batch([import_id])
    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "needs_client"
    assert "429" in row["error"]


@pytest.mark.asyncio
async def test_403_from_bookmark_host_goes_to_client_queue(
    client: AsyncClient, pool, monkeypatch
) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://www.reddit.com/r/WhatIsMyCQS/")

    async def fake_fetch(url: str):
        raise _status_error(403, url)

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "needs_client"
    assert "403" in row["error"]


@pytest.mark.asyncio
async def test_403_from_third_party_api_is_a_plain_failure(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """A 403 from ScrapeCreators means our key/config is broken — sending the
    row to the user's browser can't fix that."""
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://www.youtube.com/watch?v=abc")

    async def fake_transcript(url: str) -> dict:
        raise _status_error(403, "https://api.scrapecreators.com/v1/youtube/video/transcript")

    monkeypatch.setattr(clip_router.youtube_transcript, "fetch_transcript", fake_transcript)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "failed"
    assert "api.scrapecreators.com" in row["error"]


@pytest.mark.asyncio
async def test_exhausted_attempts_resolve_link_only(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/flaky", title="Flaky")
    await pool.execute(
        "UPDATE url_imports SET status = 'failed', attempts = 2 WHERE id = $1", import_id
    )

    async def fake_fetch(url: str):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert "ConnectError" in row["error"]
    bookmarks = await _bookmark_rows(pool, owner_id)
    assert len(bookmarks) == 1
    assert "Flaky" in bookmarks[0].values()


# --- Windowed dispatch ---


@pytest.mark.asyncio
async def test_top_up_caps_in_flight_urls(client: AsyncClient, pool, monkeypatch) -> None:
    dispatched: list[list[str]] = []
    monkeypatch.setattr(
        clips_tasks.process_url_imports, "delay", lambda ids: dispatched.append(ids)
    )
    _, owner_id = await _register(client)
    await url_import_service.create_url_imports(
        owner_user_id=UUID(owner_id),
        created_by=UUID(owner_id),
        items=[{"url": f"https://example.com/{i}"} for i in range(clips_tasks.WINDOW_URLS + 50)],
    )

    first = await clips_tasks.top_up_url_imports()
    assert first == clips_tasks.WINDOW_URLS
    assert sum(len(chunk) for chunk in dispatched) == clips_tasks.WINDOW_URLS

    # The window is full (dispatched rows count as in flight) — a second
    # sweep must not dispatch the remainder yet.
    assert await clips_tasks.top_up_url_imports() == 0


def test_interleave_by_domain_round_robins() -> None:
    rows = [
        {"url": "https://a.example/1"},
        {"url": "https://a.example/2"},
        {"url": "https://a.example/3"},
        {"url": "https://b.example/1"},
        {"url": "https://c.example/1"},
    ]
    ordered = [r["url"] for r in clips_tasks._interleave_by_domain(rows)]
    assert ordered == [
        "https://a.example/1",
        "https://b.example/1",
        "https://c.example/1",
        "https://a.example/2",
        "https://a.example/3",
    ]


# --- Extension-fed hydration (client queue) ---


async def _needs_client_row(pool, owner_id: str, url: str, title: str | None = None) -> UUID:
    import_id = await _make_import(owner_id, url, title)
    await url_import_service.mark_needs_client(import_id, "HTTP 403")
    return import_id


@pytest.mark.asyncio
async def test_client_queue_claims_are_owner_scoped_and_leased(client: AsyncClient, pool) -> None:
    headers, owner_id = await _register(client)
    other_headers, _ = await _register(client)
    import_id = await _needs_client_row(pool, owner_id, "https://example.com/walled")

    other = await client.get("/api/v1/me/imports/client-queue", headers=other_headers)
    assert other.json()["items"] == []

    mine = await client.get("/api/v1/me/imports/client-queue", headers=headers)
    assert [i["id"] for i in mine.json()["items"]] == [str(import_id)]

    # Claimed rows are leased — an immediate re-poll must not hand them out again.
    again = await client.get("/api/v1/me/imports/client-queue", headers=headers)
    assert again.json()["items"] == []


@pytest.mark.asyncio
async def test_client_result_html_hydrates_the_clip(client: AsyncClient, pool) -> None:
    headers, owner_id = await _register(client)
    import_id = await _needs_client_row(pool, owner_id, "https://example.com/walled")

    resp = await client.post(
        f"/api/v1/me/imports/{import_id}/client-result",
        json={"html": ARTICLE_HTML},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert row["error"] is None
    page = await pool.fetchrow("SELECT name FROM pages WHERE id = $1", row["result_page_id"])
    assert page["name"] == "Why Simplicity Wins"


@pytest.mark.asyncio
async def test_client_result_error_saves_link_only(client: AsyncClient, pool) -> None:
    headers, owner_id = await _register(client)
    import_id = await _needs_client_row(
        pool, owner_id, "https://example.com/walled", title="Walled"
    )

    resp = await client.post(
        f"/api/v1/me/imports/{import_id}/client-result",
        json={"error": "HTTP 403"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "link_only"

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert "client fetch failed" in row["error"]
    bookmarks = await _bookmark_rows(pool, owner_id)
    assert "Walled" in bookmarks[0].values()


@pytest.mark.asyncio
async def test_client_result_rejects_wrong_state_and_bad_body(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    import_id = await _make_import(owner_id, "https://example.com/normal")

    wrong_state = await client.post(
        f"/api/v1/me/imports/{import_id}/client-result",
        json={"html": "<html></html>"},
        headers=headers,
    )
    assert wrong_state.status_code == 409

    await url_import_service.mark_needs_client(import_id, "HTTP 403")
    both = await client.post(
        f"/api/v1/me/imports/{import_id}/client-result",
        json={"html": "<html></html>", "error": "x"},
        headers=headers,
    )
    assert both.status_code == 422
    neither = await client.post(
        f"/api/v1/me/imports/{import_id}/client-result", json={}, headers=headers
    )
    assert neither.status_code == 422


@pytest.mark.asyncio
async def test_needs_client_rows_expire_to_link_only(client: AsyncClient, pool) -> None:
    _, owner_id = await _register(client)
    import_id = await _needs_client_row(
        pool, owner_id, "https://example.com/walled", title="Walled"
    )
    await pool.execute(
        "UPDATE url_imports SET updated_at = now() - INTERVAL '25 hours' WHERE id = $1",
        import_id,
    )

    expired = await clips_tasks._expire_needs_client()
    assert expired == 1
    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    assert "no browser extension" in row["error"]
    bookmarks = await _bookmark_rows(pool, owner_id)
    assert "Walled" in bookmarks[0].values()
