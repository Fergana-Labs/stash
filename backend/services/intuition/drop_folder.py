"""Drop folders: each eval can have a Files folder where people add examples over time.

Every file or page added to the folder becomes one unlabeled example (needs review) in
the eval, read the same way as an upload in the wizard. Imports are recorded so a file
is taken once; files that cannot be read are recorded with the reason and skipped.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ...database import get_pool
from .. import files_tree_service, storage_service
from . import builder, service, trace_examples

log = logging.getLogger(__name__)

# Bounds one sync so a big drop does not hold a worker (images each take a vision call).
MAX_PER_SYNC = 20


def folder_url(folder_id: UUID) -> str:
    return f"/folders/{folder_id}"


async def get(owner_id: UUID, model_id: UUID) -> dict | None:
    """The eval's drop folder with how many items it has supplied, or None."""
    row = await get_pool().fetchrow(
        """SELECT f.id, f.name,
                  (SELECT count(*) FROM intuition_drop_imports i
                    WHERE i.model_id = m.id AND i.example_id IS NOT NULL) AS imported
             FROM intuition_models m JOIN folders f ON f.id = m.drop_folder_id
            WHERE m.id = $1 AND m.owner_user_id = $2""",
        model_id,
        owner_id,
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "url": folder_url(row["id"]),
        "imported": row["imported"],
    }


async def ensure(owner_id: UUID, model_id: UUID, created_by: UUID) -> dict:
    """The eval's drop folder, created as "<eval name> examples" on first use."""
    existing = await get(owner_id, model_id)
    if existing:
        return existing
    model = await get_pool().fetchrow(
        "SELECT name FROM intuition_models WHERE id = $1 AND owner_user_id = $2",
        model_id,
        owner_id,
    )
    if not model:
        raise service.NotFound("Eval not found")
    folder = await files_tree_service._create_folder_unique(
        owner_id, f"{model['name']} examples", created_by, None, max_length=255
    )
    await get_pool().execute(
        "UPDATE intuition_models SET drop_folder_id = $3 WHERE id = $1 AND owner_user_id = $2",
        model_id,
        owner_id,
        folder["id"],
    )
    return await get(owner_id, model_id)


async def _new_objects(model_id: UUID, folder_id: UUID, limit: int) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT 'file' AS object_type, f.id, f.name, f.content_type, f.storage_key,
                  NULL::text AS text, f.created_at
             FROM files f
            WHERE f.folder_id = $2 AND f.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM intuition_drop_imports i WHERE i.model_id = $1
                              AND i.object_type = 'file' AND i.object_id = f.id)
           UNION ALL
           SELECT 'page', p.id, p.name, p.content_type, NULL,
                  CASE WHEN p.content_type = 'html' THEN p.content_html ELSE p.content_markdown END,
                  p.created_at
             FROM pages p
            WHERE p.folder_id = $2 AND p.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM intuition_drop_imports i WHERE i.model_id = $1
                              AND i.object_type = 'page' AND i.object_id = p.id)
            ORDER BY created_at
            LIMIT $3""",
        model_id,
        folder_id,
        limit,
    )
    return [dict(r) for r in rows]


async def _item(obj: dict) -> dict:
    if obj["object_type"] == "page":
        text = (obj["text"] or "").strip()
        if not text:
            raise ValueError("The page is empty")
        return {"kind": "document", "name": obj["name"], "content": text[: builder.MAX_TEXT]}
    data = await storage_service.download_file(obj["storage_key"])
    return await builder.read_input(
        data, obj["name"], obj["content_type"] or "application/octet-stream"
    )


async def _trace_rows(owner_id: UUID, model_id: UUID, obj: dict) -> list[dict] | None:
    """An agent trace becomes one example per moment the user reacted to, with suggested
    labels; None when the object is not a trace file."""
    if obj["object_type"] != "file" or not obj["name"].lower().endswith((".jsonl", ".ndjson")):
        return None
    data = await storage_service.download_file(obj["storage_key"])
    labels, description = await trace_examples.eval_labels(owner_id, model_id)
    return await trace_examples.examples(
        description, labels, data.decode("utf-8", errors="replace"), obj["name"]
    )


async def sync(model_id: UUID) -> dict:
    """Import the folder's new files and pages as unlabeled examples."""
    model = await get_pool().fetchrow(
        "SELECT owner_user_id, drop_folder_id FROM intuition_models WHERE id = $1", model_id
    )
    if not model or not model["drop_folder_id"]:
        return {"added": 0, "failed": 0}
    added = failed = 0
    for obj in await _new_objects(model_id, model["drop_folder_id"], MAX_PER_SYNC):
        example_id, error = None, None
        try:
            rows = await _trace_rows(model["owner_user_id"], model_id, obj)
            if rows is None:
                item = await _item(obj)
                rows = [
                    {
                        "item": item,
                        "needs_review": True,
                        "note": f"From the drop folder: {obj['name']}",
                    }
                ]
            created = (
                await service.add_examples(model["owner_user_id"], model_id, rows, "human")
                if rows
                else []
            )
            example_id = created[0]["id"] if created else None
            added += len(created)
        except Exception as exc:  # noqa: BLE001 -- record and move on; one bad file must not block the rest
            log.warning(
                "drop folder import failed for %s %s: %s", obj["object_type"], obj["id"], exc
            )
            error = str(exc)[:500] or type(exc).__name__
            failed += 1
        await get_pool().execute(
            """INSERT INTO intuition_drop_imports (model_id, object_type, object_id, example_id, error)
               VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING""",
            model_id,
            obj["object_type"],
            obj["id"],
            example_id,
            error,
        )
    return {"added": added, "failed": failed}


async def due() -> list[UUID]:
    """Evals whose drop folder has something not yet imported (a cheap check for the beat tick)."""
    ids = await get_pool().fetch(
        """SELECT m.id FROM intuition_models m
            WHERE m.drop_folder_id IS NOT NULL
              AND (EXISTS (SELECT 1 FROM files f WHERE f.folder_id = m.drop_folder_id
                             AND f.deleted_at IS NULL
                             AND NOT EXISTS (SELECT 1 FROM intuition_drop_imports i
                                              WHERE i.model_id = m.id AND i.object_type = 'file'
                                                AND i.object_id = f.id))
                   OR EXISTS (SELECT 1 FROM pages p WHERE p.folder_id = m.drop_folder_id
                                AND p.deleted_at IS NULL
                                AND NOT EXISTS (SELECT 1 FROM intuition_drop_imports i
                                                 WHERE i.model_id = m.id AND i.object_type = 'page'
                                                   AND i.object_id = p.id)))"""
    )
    return [row["id"] for row in ids]
