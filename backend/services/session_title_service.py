"""Readable titles for sessions."""

from __future__ import annotations

import re

MAX_TITLE_LENGTH = 80

_USER_EVENT_TYPES = (
    "user_message",
    "user_prompt",
    "prompt",
    "message",
    "user",
)
_ASSISTANT_EVENT_TYPES = ("assistant_message", "assistant")


def title_from_text(text: str | None, session_id: str) -> str:
    title = _title_from_content(text)
    if title:
        return _truncate(title)
    return session_id


def title_from_events(events: list[dict], session_id: str) -> str:
    for event_type in (_USER_EVENT_TYPES, _ASSISTANT_EVENT_TYPES):
        title = _title_from_first_matching_event(events, event_type)
        if title:
            return _truncate(title)
    return session_id


def _title_from_first_matching_event(events: list[dict], event_types: tuple[str, ...]) -> str:
    for event in events:
        if event.get("event_type") not in event_types:
            continue
        title = _title_from_content(event.get("content"))
        if title:
            return title
    return ""


def _title_from_content(content: str | None) -> str:
    title = _title_from_structured_context(content)
    if title:
        return title

    for line in (content or "").splitlines():
        title = _title_from_line(line)
        if title:
            return title
    return ""


def _title_from_structured_context(content: str | None) -> str:
    lines = (content or "").splitlines()
    first_line = next((line.strip() for line in lines if line.strip()), "")
    if not first_line.lower().startswith("you are working on a linear ticket"):
        return ""

    for line in lines:
        match = re.match(r"^\s*Title:\s*(.+?)\s*$", line)
        if not match:
            continue
        return _title_from_line(match.group(1))

    return ""


def _title_from_line(line: str) -> str:
    text = _strip_markdown(line)
    if not text:
        return ""

    text = _strip_lead_in(text)
    if not text:
        return ""

    return _first_clause(text)


def _strip_markdown(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return text.strip(" \t*_")


def _first_clause(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.+?)[.!?](?:\s|$)", one_line)
    if match:
        return match.group(1).strip()
    return one_line


def _strip_lead_in(text: str) -> str:
    lower = text.lower()
    for phrase in ("please ", "can you ", "could you "):
        if lower.startswith(phrase):
            return _capitalize_first(text[len(phrase) :].strip())
    return text


def _truncate(title: str) -> str:
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    return title[:MAX_TITLE_LENGTH]


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]
