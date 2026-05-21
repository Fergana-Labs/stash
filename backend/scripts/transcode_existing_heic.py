"""One-off backfill: transcode every existing HEIC file in storage to JPEG.

HEIC transcode now happens at upload time, but files uploaded before
that change are still HEIC in R2. Run this once after deploying to fix
existing iPhone-photo pages.

Usage::

    python -m backend.scripts.transcode_existing_heic            # dry run
    python -m backend.scripts.transcode_existing_heic --apply    # commit

For each HEIC row in ``files``: download bytes from R2, decode + re-encode
as JPEG, upload to a new storage key (so the bucket isn't left with two
files referring to the same name), then update ``files`` with the new
storage_key, name, content_type, and size_bytes.

Idempotent — already-JPEG rows are skipped on a second run.
"""

import argparse
import asyncio
import logging

from ..database import close_db, get_pool, init_pool
from ..services import image_transcode, storage_service

logger = logging.getLogger(__name__)


async def _list_heic_rows():
    pool = get_pool()
    return await pool.fetch(
        """
        SELECT id, workspace_id, name, content_type, storage_key
        FROM files
        WHERE deleted_at IS NULL
          AND (
            lower(content_type) IN ('image/heic', 'image/heif', 'image/heic-sequence')
            OR lower(name) LIKE '%.heic'
            OR lower(name) LIKE '%.heif'
            OR lower(name) LIKE '%.hif'
          )
        ORDER BY created_at
        """
    )


async def _transcode_one(row, apply: bool) -> bool:
    file_id = row["id"]
    name = row["name"]
    storage_key = row["storage_key"]
    logger.info("HEIC %s (%s) -> downloading…", file_id, name)

    heic_bytes = await storage_service.download_file(storage_key)
    new_bytes, new_name, new_ct = await image_transcode.maybe_transcode_heic(
        heic_bytes, name, row["content_type"]
    )
    if new_ct != "image/jpeg":
        logger.warning("HEIC %s skipped (transcoder returned %s)", file_id, new_ct)
        return False

    logger.info("HEIC %s -> %s (%d B -> %d B)", file_id, new_name, len(heic_bytes), len(new_bytes))
    if not apply:
        return True

    new_storage_key = await storage_service.upload_file(
        str(row["workspace_id"]), new_name, new_bytes, new_ct
    )
    pool = get_pool()
    await pool.execute(
        """
        UPDATE files
        SET name = $1,
            content_type = $2,
            size_bytes = $3,
            storage_key = $4
        WHERE id = $5
        """,
        new_name,
        new_ct,
        len(new_bytes),
        new_storage_key,
        file_id,
    )
    # Best-effort: drop the old HEIC blob. delete_file is safe if missing.
    try:
        await storage_service.delete_file(storage_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HEIC %s old-blob delete failed: %s", file_id, exc)
    return True


async def main(apply: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    await init_pool()
    rows = await _list_heic_rows()
    logger.info("found %d HEIC file row(s)%s", len(rows), "" if apply else " (dry run)")
    converted = 0
    for row in rows:
        try:
            if await _transcode_one(row, apply):
                converted += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("HEIC %s failed: %s", row["id"], exc)
    logger.info("done. %s %d file(s).", "converted" if apply else "would convert", converted)
    await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
