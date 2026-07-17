"""Index bounded PostHog project objects through its read-only MCP server."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from ...services import source_service
from ..storage import get_valid_token
from .client import call_tool, posthog_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_OBJECTS_PER_KIND = 1000
SEARCH_LIMIT = 25
KINDS = {
    "dashboards": {"label": "dashboard", "list": "dashboards-get-all", "get": "dashboard-get"},
    "insights": {"label": "insight", "list": "insights-list", "get": "insight-get"},
    "feature_flags": {
        "label": "feature flag",
        "list": "feature-flag-get-all",
        "get": "feature-flag-get-definition",
    },
    "experiments": {"label": "experiment", "list": "experiment-list", "get": "experiment-get"},
}


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _path_segment(value: str) -> str:
    return " ".join(value.replace("/", "-").split())[:100].strip()


def _object_name(kind: str, item: dict) -> str:
    if kind == "feature_flags":
        return item.get("key") or item.get("name") or str(item["id"])
    return item.get("name") or f"Untitled {KINDS[kind]['label']}"


def _object_path(kind: str, item: dict) -> str:
    return f"{kind}/{_path_segment(_object_name(kind, item))} ({item['id']})"


def _results(payload: dict) -> list[dict]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("PostHog list tool returned no results array")
    return results


async def index_posthog(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "posthog")
    present: list[str] = []
    async with posthog_session(token) as session:
        for kind, config in KINDS.items():
            offset = 0
            while offset < MAX_OBJECTS_PER_KIND:
                items = _results(
                    await call_tool(session, config["list"], {"limit": PAGE_SIZE, "offset": offset})
                )
                for item in items:
                    path = _object_path(kind, item)
                    await source_service.upsert_index_row(
                        table="posthog_index",
                        source_id=source_id,
                        owner_user_id=owner_user_id,
                        path=path,
                        name=_object_name(kind, item),
                        kind=config["label"],
                        external_ref=f"{kind}:{item['id']}",
                        external_updated_at=_parse_time(
                            item.get("updated_at") or item.get("created_at")
                        ),
                    )
                    present.append(path)
                if len(items) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
    await source_service.remove_missing_documents("posthog_index", source_id, present)
    logger.info("posthog source %s: indexed %d object(s)", source_id, len(present))
    return None


async def fetch_posthog_content(owner_user_id: UUID, external_ref: str) -> str:
    kind, separator, object_id = external_ref.partition(":")
    if not separator or kind not in KINDS or not object_id:
        raise ValueError("invalid PostHog object reference")
    token = await get_valid_token(owner_user_id, "posthog")
    async with posthog_session(token) as session:
        item = await call_tool(session, KINDS[kind]["get"], {"id": object_id})
    name = _object_name(kind, item)
    description = item.get("description") or item.get("name") or ""
    parts = [f"# {name}", f"Type: {KINDS[kind]['label']}"]
    if description and description != name:
        parts.append(f"\n{description}")
    parts.append("\n## Details\n```json\n" + json.dumps(item, indent=2, sort_keys=True) + "\n```")
    return "\n".join(parts)


async def search_posthog(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "posthog")
    items: list[tuple[str, dict]] = []
    async with posthog_session(token) as session:
        for kind, config in KINDS.items():
            payload = await call_tool(session, config["list"], {"search": query, "limit": limit})
            items.extend((kind, item) for item in _results(payload))
    refs = [f"{kind}:{item['id']}" for kind, item in items]
    paths = await source_service.index_paths_for_refs("posthog_index", UUID(source["id"]), refs)
    hits = []
    for kind, item in items:
        indexed = paths.get(f"{kind}:{item['id']}")
        if indexed is None:
            continue
        path, name = indexed
        hits.append(
            {
                "ref": path,
                "name": name,
                "snippet": item.get("description") or item.get("name") or "",
            }
        )
        if len(hits) == limit:
            break
    return hits
