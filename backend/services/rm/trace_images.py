"""Keep trace image bytes out of polled trace JSON and classifier inputs."""

import asyncio
import base64
import binascii
import logging
import os
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from ...database import get_pool
from .. import storage_service

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


def decode_image(data_url: str):
    header, _, encoded = data_url.partition(",")
    if not header.endswith(";base64") or len(encoded) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            return None
        with Image.open(BytesIO(data)) as image:
            content_type = FORMATS.get(image.format)
            if not content_type or image.width * image.height > 40_000_000:
                return None
            width, height = image.size
            image.verify()
        return data, content_type, width, height
    except (
        ValueError,
        binascii.Error,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return None


async def store_images(conn, owner: UUID, trace_id: UUID, steps) -> None:
    if not any(step.images for step in steps):
        return
    local_dir = os.environ.get("STASH_TRACE_IMAGE_DIR")
    if not storage_service.is_configured() and not local_dir:
        logger.warning("Trace images could not be saved: private image storage is unavailable")
        return
    rows = await conn.fetch(
        "SELECT id,idx FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", trace_id
    )
    existing = {
        (row["step_id"], row["position"])
        for row in await conn.fetch(
            "SELECT i.step_id,i.position FROM rm_trace_images i JOIN rm_trace_steps s ON s.id=i.step_id WHERE s.trace_id=$1",
            trace_id,
        )
    }
    for row in rows:
        if row["idx"] >= len(steps):
            continue
        for position, image in enumerate(steps[row["idx"]].images):
            if (row["id"], position) in existing:
                continue
            decoded = await asyncio.to_thread(decode_image, image.data_url)
            if decoded is None:
                continue
            data, content_type, width, height = decoded
            image_id = uuid4()
            # Explicit opt-in for local development; production uses private S3.
            try:
                if storage_service.is_configured():
                    key = await storage_service.upload_file(
                        str(owner), str(image_id), data, content_type
                    )
                else:
                    root = Path(local_dir)
                    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
                    await asyncio.to_thread((root / image_id.hex).write_bytes, data)
                    key = f"local:{image_id.hex}"
            except (httpx.HTTPError, OSError):
                # A transient attachment failure must not lose the transcript.
                # A later snapshot can backfill the missing image.
                logger.warning("Could not save trace image %s; a later upload can retry", image_id)
                continue
            await conn.execute(
                """INSERT INTO rm_trace_images
                (id,step_id,position,source_start,source_end,content_type,width,height,storage_key)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                image_id,
                row["id"],
                position,
                image.start,
                image.end,
                content_type,
                width,
                height,
                key,
            )


async def for_trace(trace_id: UUID) -> dict:
    result = {}
    rows = await get_pool().fetch(
        """SELECT i.id,i.step_id,i.source_start,i.source_end,i.width,i.height
        FROM rm_trace_images i JOIN rm_trace_steps s ON s.id=i.step_id
        WHERE s.trace_id=$1 ORDER BY i.position""",
        trace_id,
    )
    for row in rows:
        result.setdefault(row["step_id"], []).append(
            {
                "id": row["id"],
                "start": row["source_start"],
                "end": row["source_end"],
                "width": row["width"],
                "height": row["height"],
            }
        )
    return result


async def read_image(user_id: UUID, image_id: UUID):
    row = await get_pool().fetchrow(
        """SELECT i.storage_key,i.content_type FROM rm_trace_images i
        JOIN rm_trace_steps s ON s.id=i.step_id JOIN rm_traces t ON t.id=s.trace_id
        WHERE i.id=$1 AND (t.owner_user_id=$2 OR EXISTS
            (SELECT 1 FROM rm_wb_trace_reviewers r WHERE r.trace_id=t.id AND r.user_id=$2))""",
        image_id,
        user_id,
    )
    if row is None:
        raise LookupError("Image not found")
    key = row["storage_key"]
    if key.startswith("local:"):
        root = os.environ.get("STASH_TRACE_IMAGE_DIR")
        if not root:
            raise LookupError("Image not found")
        try:
            data = await asyncio.to_thread((Path(root) / UUID(key[6:]).hex).read_bytes)
        except (FileNotFoundError, ValueError) as exc:
            raise LookupError("Image not found") from exc
    else:
        data = await storage_service.download_file(key)
    return data, row["content_type"]
