"""Heavi rules-of-the-road: live VFS rendering + the search-cache indexer.

Two consumers share the rendering helpers here:
- source_service's live branches (ls/cat) fetch the customer's endpoint on
  every read — Heavi's Postgres is the source of truth, never our copy.
- `index_heavi` periodically upserts the same rendering into
  heavi_learning_docs purely so FTS + the embedding pipeline cover the rules.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from ...services import source_service
from .client import fetch_learnings

logger = logging.getLogger(__name__)

TABLE = "heavi_learning_docs"


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _path_segment(value: str) -> str:
    return " ".join(value.replace("/", "-").split())[:80].strip()


def rule_path(rule: dict) -> str:
    return f"{_path_segment(rule['summary'])} ({rule['id']})"


def rule_name(rule: dict) -> str:
    return _path_segment(rule["summary"])


def rule_content(rule: dict) -> str:
    if rule["source_type"] == "user_feedback":
        source = f"user_feedback (candidate {rule.get('source_id') or 'unknown'})"
    else:
        source = rule["source_type"]
    lines = [
        rule["summary"],
        "",
        f"- id: {rule['id']}",
        f"- source: {source}",
        f"- created: {rule['created_at']}",
    ]
    return "\n".join(lines) + "\n"


def rule_entries(rules: list[dict], prefix: str = "") -> list[dict]:
    ordered = sorted(rules, key=lambda r: r["created_at"], reverse=True)
    entries = [
        {"path": rule_path(rule), "name": rule_name(rule), "kind": "rule"} for rule in ordered
    ]
    return [entry for entry in entries if entry["path"].startswith(prefix)]


def find_rule(rules: list[dict], path: str) -> dict | None:
    for rule in rules:
        if rule_path(rule) == path or rule["id"] == path:
            return rule
    return None


async def index_heavi(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    rules = await fetch_learnings(owner_user_id)
    present: list[str] = []
    for rule in rules:
        path = rule_path(rule)
        await source_service.upsert_content_document(
            table=TABLE,
            source_id=source_id,
            owner_user_id=owner_user_id,
            path=path,
            name=rule_name(rule),
            kind="rule",
            content=rule_content(rule),
            external_ref=rule["id"],
            external_updated_at=_parse_time(rule.get("updated_at") or rule["created_at"]),
        )
        present.append(path)
    await source_service.remove_missing_documents(TABLE, source_id, present)
    logger.info("heavi source %s: indexed %d rule(s)", source_id, len(present))
    return None
