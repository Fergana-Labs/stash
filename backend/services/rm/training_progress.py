"""Persist structured worker progress without making telemetry a job dependency."""

import asyncio
import logging
from datetime import UTC, datetime

from rm_worker.progress import parse_event

from ...database import get_pool

logger = logging.getLogger(__name__)


async def save(model_id, event):
    try:
        await get_pool().execute(
            "UPDATE rm_reward_models SET progress=$2 WHERE id=$1 AND status='running'",
            model_id,
            event,
        )
    except Exception:
        logger.warning("Could not save training progress for %s", model_id, exc_info=True)


async def stage(model_id, name):
    await save(
        model_id,
        {
            "stage": name,
            "completed": 0,
            "total": 0,
            "elapsed_seconds": 0,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


async def watch(process, log_path, model_id):
    waiter = asyncio.create_task(process.wait())
    try:
        with log_path.open(errors="replace") as stream:
            pending = ""
            while True:
                await asyncio.wait({waiter}, timeout=2)
                latest = None
                while chunk := stream.read(65536):
                    lines = (pending + chunk).split("\n")
                    pending = lines.pop()[-65536:]
                    for line in lines:
                        latest = parse_event(line) or latest
                if waiter.done():
                    latest = parse_event(pending) or latest
                if latest:
                    await save(model_id, latest)
                if waiter.done():
                    return waiter.result()
    finally:
        if not waiter.done():
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
