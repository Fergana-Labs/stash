"""Image evals: examples in, a scoring endpoint out.

A classifier is owned by one user. Its examples are images labeled liked or
disliked; each keeps its frozen embedding (embedder.py), so training is a fast
numpy fit (head.py) that never re-embeds. Every scoring call is logged with its
image, score and written comments; labeling a call turns it into an example.
"""

import asyncio
import os
import time
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from PIL import Image, UnidentifiedImageError

from ...database import get_pool
from .. import storage_service
from ..image_transcode import maybe_transcode_heic
from . import critic, embedder
from . import head as heads

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
MAX_EXAMPLES = 1000


class NotFound(LookupError):
    pass


class StorageUnavailable(RuntimeError):
    pass


class Conflict(RuntimeError):
    pass


# ── Images ───────────────────────────────────────────────────────────────


async def validate_image(data: bytes, filename: str, content_type: str) -> tuple[bytes, str]:
    """Return (bytes, content_type) for a supported image, converting HEIC to JPEG."""
    data, _, content_type = await maybe_transcode_heic(data, filename, content_type or "")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"{filename or 'image'} is larger than 15 MB")
    try:
        with Image.open(BytesIO(data)) as image:
            kind = FORMATS.get(image.format or "")
            if not kind or image.width * image.height > MAX_PIXELS:
                raise ValueError(
                    f"{filename or 'image'} must be a PNG, JPEG, GIF or WEBP under 60 megapixels"
                )
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError(f"{filename or 'image'} is not a readable image") from exc
    return data, kind


def _local_dir() -> Path | None:
    root = os.environ.get("IMAGE_EVAL_IMAGE_DIR")
    return Path(root) if root else None


async def _store(owner: UUID, data: bytes, content_type: str) -> str:
    image_id = uuid4().hex
    if storage_service.is_configured():
        return await storage_service.upload_file(str(owner), image_id, data, content_type)
    root = _local_dir()
    if root is None:
        raise StorageUnavailable("Image storage is not configured")
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread((root / image_id).write_bytes, data)
    return f"local:{image_id}"


async def _read(key: str) -> bytes:
    if key.startswith("local:"):
        root = _local_dir()
        if root is None:
            raise NotFound("Image not found")
        try:
            return await asyncio.to_thread((root / UUID(key[6:]).hex).read_bytes)
        except (FileNotFoundError, ValueError) as exc:
            raise NotFound("Image not found") from exc
    return await storage_service.download_file(key)


# ── Classifiers ──────────────────────────────────────────────────────────


def _summary(row) -> dict:
    metrics = row["metrics"] or {}
    return {
        "id": row["id"],
        "model_id": row["model_id"],
        "name": row["name"],
        "description": row["description"],
        "embed_model": row["embed_model"],
        "style_brief": row["style_brief"],
        "build": row["build"],
        "trained": row["head"] is not None,
        "trained_at": row["trained_at"],
        "liked": metrics.get("liked"),
        "disliked": metrics.get("disliked"),
        "heldout_accuracy": metrics.get("heldout_accuracy"),
        "heldout_by_group": metrics.get("heldout_by_group"),
        "heldout_balanced_accuracy": metrics.get("heldout_balanced_accuracy"),
        "heldout_method": metrics.get("heldout_method"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _owned(owner: UUID, classifier_id: UUID):
    row = await get_pool().fetchrow(
        "SELECT * FROM image_evals WHERE id=$1 AND owner_user_id=$2", classifier_id, owner
    )
    if row is None:
        raise NotFound("Image eval not found")
    return row


async def create(owner: UUID, name: str, description: str, model_id: UUID | None = None) -> dict:
    row = await get_pool().fetchrow(
        """INSERT INTO image_evals (owner_user_id, name, description, embed_model, model_id)
        VALUES ($1,$2,$3,$4,$5) RETURNING *""",
        owner,
        name.strip(),
        description,
        embedder.EMBED_MODEL,
        model_id,
    )
    return _summary(row)


async def by_model(owner: UUID, model_id: UUID) -> dict | None:
    """The image eval the wizard made for this intuition model, or None."""
    classifier_id = await get_pool().fetchval(
        "SELECT id FROM image_evals WHERE model_id=$1 AND owner_user_id=$2", model_id, owner
    )
    return await get(owner, classifier_id) if classifier_id else None


async def list_classifiers(owner: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT c.*, (SELECT count(*) FROM image_eval_calls k WHERE k.classifier_id=c.id) AS calls,
            (SELECT count(*) FROM image_eval_examples e WHERE e.classifier_id=c.id) AS examples
        FROM image_evals c WHERE owner_user_id=$1 ORDER BY updated_at DESC""",
        owner,
    )
    return [{**_summary(r), "calls": r["calls"], "examples": r["examples"]} for r in rows]


async def get(owner: UUID, classifier_id: UUID) -> dict:
    row = await _owned(owner, classifier_id)
    counts = await get_pool().fetchrow(
        """SELECT count(*) FILTER (WHERE label='liked') AS liked,
            count(*) FILTER (WHERE label='disliked' AND source<>'imitation') AS disliked,
            count(*) FILTER (WHERE source='imitation') AS imitations,
            (SELECT count(*) FROM image_eval_calls WHERE classifier_id=$1) AS calls,
            (SELECT max(created_at) FROM image_eval_examples WHERE classifier_id=$1) AS last_example
        FROM image_eval_examples WHERE classifier_id=$1""",
        classifier_id,
    )
    stale = (
        row["head"] is not None
        and counts["last_example"] is not None
        and (row["trained_at"] is None or counts["last_example"] > row["trained_at"])
    )
    return {
        **_summary(row),
        "examples": {
            "liked": counts["liked"],
            "disliked": counts["disliked"],
            "imitations": counts["imitations"],
        },
        "calls": counts["calls"],
        "needs_training": row["head"] is None or stale,
    }


async def start_build(owner: UUID, classifier_id: UUID) -> dict:
    """Queue the one-step build (style brief, imitations, training); the page polls `build`."""
    from ...tasks import image_evals as image_eval_tasks

    row = await _owned(owner, classifier_id)
    if (row["build"] or {}).get("stage") in ("queued", "brief", "imitations", "training"):
        raise Conflict("A build is already running")
    liked = await get_pool().fetchval(
        "SELECT count(*) FROM image_eval_examples WHERE classifier_id=$1 AND label='liked'",
        classifier_id,
    )
    if liked < heads.MIN_PER_CLASS:
        raise ValueError(f"Add at least {heads.MIN_PER_CLASS} liked examples first")
    await get_pool().execute(
        "UPDATE image_evals SET build=$2, updated_at=now() WHERE id=$1",
        classifier_id,
        {"stage": "queued", "done": 0, "total": 0, "error": None, "started_at": time.time()},
    )
    try:
        image_eval_tasks.build_classifier.delay(str(classifier_id))
    except Exception as exc:
        await get_pool().execute(
            "UPDATE image_evals SET build=$2 WHERE id=$1",
            classifier_id,
            {"stage": "failed", "error": "Could not start the build; try again"},
        )
        raise StorageUnavailable("Build queue unavailable") from exc
    return await get(owner, classifier_id)


async def rename(
    owner: UUID, classifier_id: UUID, name: str | None, description: str | None
) -> dict:
    await _owned(owner, classifier_id)
    await get_pool().execute(
        """UPDATE image_evals SET name=coalesce($2,name), description=coalesce($3,description),
        updated_at=now() WHERE id=$1""",
        classifier_id,
        name.strip() if name else None,
        description,
    )
    return await get(owner, classifier_id)


async def delete(owner: UUID, classifier_id: UUID) -> None:
    await _owned(owner, classifier_id)
    await get_pool().execute("DELETE FROM image_evals WHERE id=$1", classifier_id)


# ── Examples ─────────────────────────────────────────────────────────────


async def add_examples(
    owner: UUID, classifier_id: UUID, label: str, files: list[tuple[str, bytes, str]]
) -> list[dict]:
    """files: (filename, bytes, content_type). Validates all, then stores them unembedded:
    the next build or training run embeds them (embed_pending), so an upload never waits
    on a cold GPU."""
    await _owned(owner, classifier_id)
    have = await get_pool().fetchval(
        "SELECT count(*) FROM image_eval_examples WHERE classifier_id=$1", classifier_id
    )
    if have + len(files) > MAX_EXAMPLES:
        raise ValueError(f"A classifier holds at most {MAX_EXAMPLES} examples")
    images = [(name, *await validate_image(data, name, ctype)) for name, data, ctype in files]
    keys = await asyncio.gather(*(_store(owner, data, ctype) for _, data, ctype in images))
    out = []
    for (name, _, ctype), key in zip(images, keys, strict=True):
        row = await get_pool().fetchrow(
            """INSERT INTO image_eval_examples (classifier_id,label,source,filename,image_key,content_type)
            VALUES ($1,$2,'upload',$3,$4,$5) RETURNING id,label,source,filename,note,created_at""",
            classifier_id,
            label,
            name[:300],
            key,
            ctype,
        )
        out.append(dict(row))
    await get_pool().execute("UPDATE image_evals SET updated_at=now() WHERE id=$1", classifier_id)
    return out


async def list_examples(owner: UUID, classifier_id: UUID) -> list[dict]:
    row = await _owned(owner, classifier_id)
    rows = await get_pool().fetch(
        """SELECT id,label,source,call_id,filename,note,created_at FROM image_eval_examples
        WHERE classifier_id=$1 ORDER BY created_at""",
        classifier_id,
    )
    held = {}
    if row["metrics"]:
        held = dict(
            zip(
                row["metrics"].get("example_ids", []),
                row["metrics"].get("heldout_scores", []),
                strict=False,
            )
        )
    return [{**dict(r), "heldout_score": held.get(str(r["id"]))} for r in rows]


async def delete_example(owner: UUID, classifier_id: UUID, example_id: UUID) -> None:
    await _owned(owner, classifier_id)
    deleted = await get_pool().fetchval(
        "DELETE FROM image_eval_examples WHERE id=$1 AND classifier_id=$2 RETURNING id",
        example_id,
        classifier_id,
    )
    if deleted is None:
        raise NotFound("Example not found")
    await get_pool().execute("UPDATE image_evals SET updated_at=now() WHERE id=$1", classifier_id)


async def example_image(owner: UUID, classifier_id: UUID, example_id: UUID) -> tuple[bytes, str]:
    await _owned(owner, classifier_id)
    row = await get_pool().fetchrow(
        "SELECT image_key,content_type FROM image_eval_examples WHERE id=$1 AND classifier_id=$2",
        example_id,
        classifier_id,
    )
    if row is None:
        raise NotFound("Example not found")
    return await _read(row["image_key"]), row["content_type"]


# ── Training ─────────────────────────────────────────────────────────────


EMBED_BATCH = 64


async def embed_pending(classifier_id: UUID) -> int:
    """Embed the examples uploaded since the last build or training run. Returns how many."""
    rows = await get_pool().fetch(
        "SELECT id,image_key FROM image_eval_examples WHERE classifier_id=$1 AND embedding IS NULL",
        classifier_id,
    )
    for i in range(0, len(rows), EMBED_BATCH):
        batch = rows[i : i + EMBED_BATCH]
        images = await asyncio.gather(*(_read(r["image_key"]) for r in batch))
        vectors = await embedder.embed(list(images))
        for r, vector in zip(batch, vectors, strict=True):
            await get_pool().execute(
                "UPDATE image_eval_examples SET embedding=$2 WHERE id=$1", r["id"], vector
            )
    return len(rows)


CONTRAST = Path(__file__).with_name("contrast.npz")
_contrast: np.ndarray | None = None


def contrast() -> np.ndarray:
    """Embeddings of the shared off-style set (backend/scripts/build_image_eval_contrast.py):
    every eval also learns from these what is clearly not its style, so an eval built only
    from images in the style still has something to say no to."""
    global _contrast
    if _contrast is None:
        if not CONTRAST.exists():
            _contrast = np.zeros((0, 0))
        else:
            data = np.load(CONTRAST)
            same_model = str(data["embed_model"]) == embedder.EMBED_MODEL
            _contrast = data["embeddings"].astype(np.float64) if same_model else np.zeros((0, 0))
    return _contrast


def _group(row) -> str:
    if row["label"] == "liked":
        return "liked"
    return "imitation" if row["source"] == "imitation" else "disliked"


async def train(owner: UUID, classifier_id: UUID) -> dict:
    await _owned(owner, classifier_id)
    await embed_pending(classifier_id)
    rows = await get_pool().fetch(
        "SELECT id,label,source,embedding FROM image_eval_examples WHERE classifier_id=$1 ORDER BY created_at",
        classifier_id,
    )
    if len(rows) == 0:
        raise ValueError("Add liked and disliked examples first")
    x = np.array([r["embedding"] for r in rows], dtype=np.float64)
    y = np.array([r["label"] == "liked" for r in rows])
    groups = np.array([_group(r) for r in rows])
    off = contrast()
    if len(off) and off.shape[1] == x.shape[1]:
        x = np.vstack([x, off])
        y = np.concatenate([y, np.zeros(len(off), dtype=bool)])
        groups = np.concatenate([groups, np.full(len(off), "offstyle")])
    fitted, metrics = await asyncio.to_thread(heads.train, x, y, groups)
    # Only the eval's own examples have ids; the shared off-style rows are summarized by group.
    metrics["heldout_scores"] = metrics["heldout_scores"][: len(rows)]
    metrics["example_ids"] = [str(r["id"]) for r in rows]
    await get_pool().execute(
        "UPDATE image_evals SET head=$2, metrics=$3, trained_at=now(), updated_at=now() WHERE id=$1",
        classifier_id,
        fitted,
        metrics,
    )
    return await get(owner, classifier_id)


# ── Scoring and the call log ─────────────────────────────────────────────


async def score(
    owner: UUID,
    classifier_id: UUID,
    data: bytes,
    content_type: str,
    *,
    caller: str = "",
    task: str = "",
    comments: bool = True,
    filename: str = "",
) -> dict:
    row = await _owned(owner, classifier_id)
    if row["head"] is None:
        raise ValueError("Train the classifier before scoring")
    data, content_type = await validate_image(data, filename, content_type)
    # The number and the feedback come from Claude grading each trait of the style
    # (critic.judge). The embedding is kept so a labeled call can become an example.
    (vector,), judged = await asyncio.gather(
        embedder.embed([data]), critic.judge(classifier_id, row["name"], data, with_fixes=comments)
    )
    value = judged["score"]
    notes = {k: judged[k] for k in ("traits", "summary", "fixes", "keep")}
    key = await _store(owner, data, content_type)
    call = await get_pool().fetchrow(
        """INSERT INTO image_eval_calls (classifier_id,caller,task,image_key,content_type,embedding,score,comments,trained_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id,created_at""",
        classifier_id,
        caller[:100],
        task[:500],
        key,
        content_type,
        vector,
        value,
        notes,
        row["trained_at"],
    )
    return {
        "call_id": call["id"],
        "score": round(value, 4),
        "label": "liked" if value >= 0.5 else "disliked",
        "traits": notes["traits"],
        "summary": notes["summary"],
        "fixes": notes["fixes"],
        "keep": notes["keep"],
        "created_at": call["created_at"],
    }


async def list_calls(owner: UUID, classifier_id: UUID, limit: int = 100) -> list[dict]:
    await _owned(owner, classifier_id)
    rows = await get_pool().fetch(
        """SELECT k.id,k.caller,k.task,k.score,k.comments,k.created_at,
            e.label AS feedback_label, e.note AS feedback_note
        FROM image_eval_calls k LEFT JOIN image_eval_examples e ON e.call_id=k.id
        WHERE k.classifier_id=$1 ORDER BY k.created_at DESC LIMIT $2""",
        classifier_id,
        limit,
    )
    return [dict(r) for r in rows]


async def call_image(owner: UUID, classifier_id: UUID, call_id: UUID) -> tuple[bytes, str]:
    await _owned(owner, classifier_id)
    row = await get_pool().fetchrow(
        "SELECT image_key,content_type FROM image_eval_calls WHERE id=$1 AND classifier_id=$2",
        call_id,
        classifier_id,
    )
    if row is None:
        raise NotFound("Call not found")
    return await _read(row["image_key"]), row["content_type"]


async def label_call(
    owner: UUID, classifier_id: UUID, call_id: UUID, label: str | None, note: str
) -> dict:
    """Label a scored image as liked/disliked (it becomes an example), or clear the label (None)."""
    await _owned(owner, classifier_id)
    call = await get_pool().fetchrow(
        "SELECT * FROM image_eval_calls WHERE id=$1 AND classifier_id=$2", call_id, classifier_id
    )
    if call is None:
        raise NotFound("Call not found")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM image_eval_examples WHERE call_id=$1", call_id)
        if label is not None:
            await conn.execute(
                """INSERT INTO image_eval_examples (classifier_id,label,source,call_id,filename,note,image_key,content_type,embedding)
                VALUES ($1,$2,'call',$3,$4,$5,$6,$7,$8)""",
                classifier_id,
                label,
                call_id,
                call["task"][:300],
                note,
                call["image_key"],
                call["content_type"],
                call["embedding"],
            )
        await conn.execute("UPDATE image_evals SET updated_at=now() WHERE id=$1", classifier_id)
    return {"call_id": call_id, "feedback_label": label, "feedback_note": note if label else None}
