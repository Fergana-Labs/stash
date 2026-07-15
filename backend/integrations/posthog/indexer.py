"""PostHog project object index.

The source indexes bounded product configuration rather than high-volume event
or person data. Object bodies are fetched live on read so analytics results and
experiment state do not go stale between syncs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token
from .provider import decode_credentials

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_OBJECTS_PER_KIND = 1000
SEARCH_LIMIT = 25
KINDS = {
    "dashboards": "dashboard",
    "insights": "insight",
    "feature_flags": "feature flag",
    "experiments": "experiment",
}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _path_segment(value: str) -> str:
    return " ".join(value.replace("/", "-").split())[:100].strip()


def _object_name(kind: str, item: dict) -> str:
    if kind == "feature_flags":
        return item.get("key") or item.get("name") or str(item["id"])
    return item.get("name") or f"Untitled {KINDS[kind]}"


def _object_path(kind: str, item: dict) -> str:
    return f"{kind}/{_path_segment(_object_name(kind, item))} ({item['id']})"


async def _client(owner_user_id: UUID) -> tuple[httpx.AsyncClient, dict[str, str]]:
    credentials = decode_credentials(await get_valid_token(owner_user_id, "posthog"))
    client = httpx.AsyncClient(
        timeout=60.0,
        headers={"Authorization": f"Bearer {credentials['personal_api_key']}"},
        base_url=credentials["instance_url"],
    )
    return client, credentials


async def index_posthog(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    client, credentials = await _client(owner_user_id)
    present: list[str] = []
    async with client:
        for kind, item_kind in KINDS.items():
            offset = 0
            while offset < MAX_OBJECTS_PER_KIND:
                response = await client.get(
                    f"/api/projects/{credentials['project_id']}/{kind}/",
                    params={"limit": PAGE_SIZE, "offset": offset},
                )
                response.raise_for_status()
                items = response.json().get("results", [])
                for item in items:
                    if item.get("deleted"):
                        continue
                    path = _object_path(kind, item)
                    await source_service.upsert_index_row(
                        table="posthog_index",
                        source_id=source_id,
                        owner_user_id=owner_user_id,
                        path=path,
                        name=_object_name(kind, item),
                        kind=item_kind,
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

    client, credentials = await _client(owner_user_id)
    async with client:
        response = await client.get(
            f"/api/projects/{credentials['project_id']}/{kind}/{object_id}/"
        )
        response.raise_for_status()
        item = response.json()

    name = _object_name(kind, item)
    description = item.get("description") or item.get("name") or ""
    parts = [f"# {name}", f"Type: {KINDS[kind]}"]
    if description and description != name:
        parts.append(f"\n{description}")
    parts.append("\n## Details\n```json\n" + json.dumps(item, indent=2, sort_keys=True) + "\n```")
    return "\n".join(parts)


async def search_posthog(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Search the four bounded object collections and resolve hits to index paths."""
    owner_user_id = UUID(source["owner_user_id"])
    client, credentials = await _client(owner_user_id)
    items: list[tuple[str, dict]] = []
    async with client:
        for kind in KINDS:
            response = await client.get(
                f"/api/projects/{credentials['project_id']}/{kind}/",
                params={"search": query, "limit": limit},
            )
            response.raise_for_status()
            items.extend((kind, item) for item in response.json().get("results", []))

    refs = [f"{kind}:{item['id']}" for kind, item in items]
    paths = await source_service.index_paths_for_refs("posthog_index", UUID(source["id"]), refs)
    hits = []
    for kind, item in items:
        ref = f"{kind}:{item['id']}"
        indexed = paths.get(ref)
        if not indexed:
            continue
        path, name = indexed
        hits.append(
            {
                "ref": path,
                "name": name,
                "snippet": item.get("description") or item.get("name") or "",
            }
        )
        if len(hits) >= limit:
            break
    return hits
