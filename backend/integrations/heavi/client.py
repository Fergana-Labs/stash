"""HTTP client for a customer's Heavi learnings endpoint.

The endpoint contract (implemented on Heavi's side, bearer-token variant of
their existing GET /api/learnings): a GET that returns the org's learnings
("rules of the road") as a bare JSON array of
`{id, summary, source_type, source_id?, created_at, updated_at?}`.
Heavi's Postgres stays the source of truth — every VFS read hits this
endpoint live; Stash only caches a copy for search/embeddings.
"""

from __future__ import annotations

import json
from uuid import UUID

import httpx

from ..storage import get_valid_token

REQUIRED_FIELDS = ("id", "summary", "source_type", "created_at")


async def fetch_learnings(owner_user_id: UUID) -> list[dict]:
    creds = json.loads(await get_valid_token(owner_user_id, "heavi"))
    return await fetch_learnings_with(creds["base_url"], creds["api_token"])


async def fetch_learnings_with(base_url: str, api_token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_token}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        resp = await client.get(base_url)
        resp.raise_for_status()
        payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError("Heavi learnings endpoint did not return a JSON array")
    for item in payload:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(field), str) for field in REQUIRED_FIELDS
        ):
            raise ValueError(
                f"Heavi learning row missing required fields ({', '.join(REQUIRED_FIELDS)})"
            )
    return payload
