"""Gmail → gmail_index indexer (index only; search/read federated).

Sync stores recent message metadata only. Search runs Gmail's native query live,
upserts returned metadata so the result can be opened, and lazy reads fetch the
full message body with the owner's token. Stash never copies message bodies
during scheduled sync.
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


async def _list_message_refs(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict]:
    resp = await client.get(
        MESSAGES_URL,
        params={"q": query, "maxResults": min(limit, 100)},
    )
    resp.raise_for_status()
    return resp.json().get("messages", []) or []


async def _get_message_metadata(client: httpx.AsyncClient, message_id: str) -> dict:
    resp = await client.get(
        MESSAGE_URL.format(message_id=message_id),
        params=_metadata_params("metadata"),
    )
    resp.raise_for_status()
    return resp.json()


async def _upsert_message_metadata(source: dict, message: dict) -> str | None:
    message_id = message.get("id")
    if not message_id:
        return None
    await source_service.upsert_index_row(
        table="gmail_index",
        source_id=UUID(source["id"]),
        workspace_id=UUID(source["workspace_id"]),
        path=message_id,
        name=_message_name(message),
        kind="message",
        external_ref=message_id,
        external_updated_at=_message_time(message),
    )
    return message_id


async def index_gmail(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "gmail")

    present: list[str] = []
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        refs = await _list_message_refs(client, DEFAULT_INDEX_QUERY, MAX_INDEX_MESSAGES)
        messages = await asyncio.gather(
            *(_get_message_metadata(client, ref["id"]) for ref in refs if ref.get("id"))
        )
        for message in messages:
            message_id = await _upsert_message_metadata(source, message)
            if message_id:
                present.append(message_id)

    await source_service.remove_missing_documents("gmail_index", source_id, present)
    logger.info("gmail source %s: indexed %d message(s)", source_id, len(present))
    return None


async def search_gmail(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "gmail")

    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        refs = await _list_message_refs(client, query, min(limit, SEARCH_LIMIT))
        messages = await asyncio.gather(
            *(_get_message_metadata(client, ref["id"]) for ref in refs if ref.get("id"))
        )

    hits: list[dict] = []
    for message in messages:
        message_id = await _upsert_message_metadata(source, message)
        if not message_id:
            continue
        hits.append(
            {
                "ref": message_id,
                "name": _message_name(message),
                "snippet": message.get("snippet") or "",
            }
        )
    return hits


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


async def fetch_gmail_content(owner_user_id: UUID, message_id: str) -> str:
    token = await get_valid_token(owner_user_id, "gmail")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            MESSAGE_URL.format(message_id=message_id),
            params=_metadata_params("full"),
        )
        resp.raise_for_status()
        return _render_message(resp.json())
