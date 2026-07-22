"""Gmail → gmail_index indexer (index only; search/read federated).

Sync stores recent message metadata only. Search runs Gmail's native query live,
upserts returned metadata so the result can be opened, and lazy reads fetch the
full message body with the owner's token. Stash never copies message bodies
during scheduled sync.

Messages are keyed by a date-foldered path — "YYYY/MM/DD HHMM subject (id)" —
so the mailbox lists chronologically instead of as a flat pile of opaque ids
(path order is the VFS listing order).
"""

from __future__ import annotations

import asyncio
import base64
import html
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
MESSAGE_URL = MESSAGES_URL + "/{message_id}"
HEADER_NAMES = ("Subject", "From", "To", "Date")
DEFAULT_INDEX_QUERY = "newer_than:30d -in:spam -in:trash"
MAX_INDEX_MESSAGES = 100
SEARCH_LIMIT = 25
# Gmail enforces a per-user quota (~250 units/sec; a metadata get costs 5), so
# an unbounded burst of 100 fetches gets 429s partway through and fails the
# whole sync. Bound the fan-out and back off on 429 before giving up.
METADATA_CONCURRENCY = 10
RETRY_DELAYS = (1.0, 2.0, 4.0)
_TAG_RE = re.compile(r"<[^>]+>")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _metadata_params(message_format: str = "metadata") -> list[tuple[str, str]]:
    params = [("format", message_format)]
    if message_format == "metadata":
        params.extend(("metadataHeaders", name) for name in HEADER_NAMES)
    return params


def _message_headers(message: dict) -> dict[str, str]:
    headers = (message.get("payload") or {}).get("headers") or []
    return {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in headers
        if header.get("name")
    }


def _message_name(message: dict) -> str:
    headers = _message_headers(message)
    subject = headers.get("subject") or "(no subject)"
    sender = headers.get("from") or ""
    if sender:
        return f"{subject} ({sender})"
    return subject


def _message_time(message: dict) -> datetime | None:
    raw = message.get("internalDate")
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, UTC)
    except (TypeError, ValueError):
        return None


def _path_segment(text: str, max_len: int = 60) -> str:
    """A string safe to embed in an index path: no slashes (they'd read as
    folders), whitespace collapsed, capped so paths stay listable."""
    cleaned = " ".join(text.replace("/", "-").split())
    return cleaned[:max_len].strip()


def _message_path(message: dict) -> str | None:
    """Index path for a message: "YYYY/MM/DD HHMM subject (id)". Year/month
    folders group the mailbox by date and the day+time leaf prefix keeps each
    month chronological; the id suffix guarantees uniqueness. None when Gmail
    returned no id or timestamp — such a payload isn't a real message."""
    message_id = message.get("id")
    sent_at = _message_time(message)
    if not message_id or sent_at is None:
        return None
    subject = _path_segment(_message_headers(message).get("subject") or "(no subject)")
    return f"{sent_at:%Y/%m/%d %H%M} {subject} ({message_id})"


async def _list_message_refs(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> tuple[list[dict], str | None, int | None]:
    """Returns (message refs, nextPageToken, resultSizeEstimate). A nextPageToken
    means Gmail matched more than we fetched — the authoritative "there is more"
    signal; resultSizeEstimate is Gmail's rough total-match count."""
    resp = await client.get(
        MESSAGES_URL,
        params={"q": query, "maxResults": min(limit, 100)},
    )
    resp.raise_for_status()
    body = resp.json()
    return (
        body.get("messages", []) or [],
        body.get("nextPageToken"),
        body.get("resultSizeEstimate"),
    )


async def _get_message_metadata(client: httpx.AsyncClient, message_id: str) -> dict:
    for delay in (*RETRY_DELAYS, None):
        resp = await client.get(
            MESSAGE_URL.format(message_id=message_id),
            params=_metadata_params("metadata"),
        )
        if resp.status_code != 429 or delay is None:
            break
        await asyncio.sleep(delay)
    resp.raise_for_status()
    return resp.json()


async def _get_messages_metadata(client: httpx.AsyncClient, refs: list[dict]) -> list[dict]:
    semaphore = asyncio.Semaphore(METADATA_CONCURRENCY)

    async def bounded(message_id: str) -> dict:
        async with semaphore:
            return await _get_message_metadata(client, message_id)

    return await asyncio.gather(*(bounded(ref["id"]) for ref in refs if ref.get("id")))


async def _upsert_message_metadata(source: dict, message: dict) -> str | None:
    """Upsert one message's metadata; returns its index path (the VFS ref)."""
    path = _message_path(message)
    if path is None:
        return None
    await source_service.upsert_index_row(
        table="gmail_index",
        source_id=UUID(source["id"]),
        owner_user_id=UUID(source["owner_user_id"]),
        path=path,
        name=_message_name(message),
        kind="message",
        external_ref=message["id"],
        external_updated_at=_message_time(message),
    )
    return path


async def index_gmail(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "gmail", source["external_ref"])

    present: list[str] = []
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        refs, _, _ = await _list_message_refs(client, DEFAULT_INDEX_QUERY, MAX_INDEX_MESSAGES)
        messages = await _get_messages_metadata(client, refs)
        for message in messages:
            path = await _upsert_message_metadata(source, message)
            if path:
                present.append(path)

    await source_service.remove_missing_documents("gmail_index", source_id, present)
    logger.info("gmail source %s: indexed %d message(s)", source_id, len(present))
    return None


async def search_gmail(source: dict, query: str, limit: int = SEARCH_LIMIT) -> dict:
    """Live-search the mailbox, capped at SEARCH_LIMIT. Returns
    {hits, truncated, estimated_total}: `truncated` is true when Gmail matched
    more than the cap, so callers can disclose the cut instead of passing the
    top slice off as the whole result."""
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "gmail", source["external_ref"])

    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        refs, next_page_token, estimated_total = await _list_message_refs(
            client, query, min(limit, SEARCH_LIMIT)
        )
        messages = await _get_messages_metadata(client, refs)

    hits: list[dict] = []
    for message in messages:
        path = await _upsert_message_metadata(source, message)
        if not path:
            continue
        hits.append(
            {
                "ref": path,
                "name": _message_name(message),
                "snippet": message.get("snippet") or "",
            }
        )
    return {
        "hits": hits,
        "truncated": bool(next_page_token),
        "estimated_total": estimated_total,
    }


def _decode_body_data(data: str) -> str:
    padded = data + ("=" * (-len(data) % 4))
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?is)</p\s*>", "\n\n", value)
    return html.unescape(_TAG_RE.sub("", value)).strip()


def _walk_parts(payload: dict):
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def _extract_body(payload: dict) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in _walk_parts(payload):
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        decoded = _decode_body_data(data)
        mime = part.get("mimeType")
        if mime == "text/plain":
            plain_parts.append(decoded.strip())
        elif mime == "text/html":
            html_parts.append(_html_to_text(decoded))

    parts = [part for part in (plain_parts or html_parts) if part]
    return "\n\n".join(parts).strip()


def _render_message(message: dict) -> str:
    headers = _message_headers(message)
    subject = headers.get("subject") or "(no subject)"
    parts = [f"# {subject}"]
    for label, key in (("From", "from"), ("To", "to"), ("Date", "date")):
        if headers.get(key):
            parts.append(f"{label}: {headers[key]}")
    if message.get("snippet"):
        parts.append(f"Snippet: {message['snippet']}")

    body = _extract_body(message.get("payload") or {})
    if body:
        parts.append(f"\n{body}")
    return "\n".join(parts)


async def fetch_gmail_content(owner_user_id: UUID, account_key: str, message_id: str) -> str:
    token = await get_valid_token(owner_user_id, "gmail", account_key)
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            MESSAGE_URL.format(message_id=message_id),
            params=_metadata_params("full"),
        )
        resp.raise_for_status()
        return _render_message(resp.json())
