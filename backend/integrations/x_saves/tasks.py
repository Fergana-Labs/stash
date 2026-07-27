"""Keep X OAuth grants alive between daily bookmark checks.

X rotates refresh tokens single-use and kills a grant whose refresh token
sits unused for about a day: in prod, a grant that had been refreshed every
~2h for days died with a 401 from the token endpoint on its first refresh
after the daily bookmark gate left it idle for 24h (2026-07-22). Exercising
`get_valid_token` on a short interval refreshes each access token as it
expires (~2h), keeping the refresh token rotating on the cadence X
demonstrably tolerates.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from httpx import HTTPError

from ...celery_app import celery
from ...database import get_pool
from ...tasks._celery_helpers import run_async
from .. import storage as integration_storage

logger = logging.getLogger(__name__)


@celery.task(name="backend.integrations.x_saves.keep_tokens_fresh")
def keep_tokens_fresh() -> int:
    return run_async(_keep_tokens_fresh())


async def _keep_tokens_fresh() -> int:
    rows = await get_pool().fetch(
        "SELECT user_id, account_key FROM user_integrations "
        "WHERE provider = 'x' AND access_token_encrypted IS NOT NULL"
    )
    alive = 0
    for row in rows:
        try:
            await integration_storage.get_valid_token(row["user_id"], "x", row["account_key"])
            alive += 1
        except (HTTPException, HTTPError) as exc:
            # A dead grant stays dead until the user reconnects — the daily
            # bookmark check surfaces that on the source. One user's dead
            # grant must not stop other users' tokens from being kept warm.
            logger.warning(
                "x token keep-fresh failed user=%s exception_type=%s",
                row["user_id"],
                type(exc).__name__,
            )
    return alive
