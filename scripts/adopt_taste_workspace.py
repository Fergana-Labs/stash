"""Register private existing pilot artifacts in the native product, without copying history.

Operator-only: no HTTP endpoint accepts filesystem locations. Run in the intended
backend environment. Existing reviews and workspace identity are preserved.
"""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from backend.database import close_db, get_pool, init_pool
from backend.services import taste


async def main(args):
    await init_pool()
    try:
        owner = UUID(args.owner)
        row = await taste.workspace(owner, create=True)
        probe = args.probe.resolve()
        experiment = args.experiment.resolve()
        from scripts.website_taste.probe_pipeline import load_probe

        load_probe(probe)
        # Explicit operator adoption, scoped to one account. Do not expose paths.
        await get_pool().execute(
            "UPDATE taste_workspaces SET name=$2,config=config || $3::jsonb WHERE id=$1",
            row["id"],
            args.name,
            {
                "probe": str(probe),
                "dataset": str(probe),
                "budget": str(probe),
                "experiment": str(experiment),
                "related_eval_ids": args.related_eval,
            },
        )
        print("Taste workspace ready: /reward-models/taste")
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--name", default="My website taste")
    parser.add_argument("--related-eval", action="append", default=[])
    asyncio.run(main(parser.parse_args()))
