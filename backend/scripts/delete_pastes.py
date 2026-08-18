"""Remove pastes by slug.

Stash Pages publishes anonymously and the public delete endpoint requires the
creator's edit_token, so there is no way for us to take down content someone
else published — which is how 13 payment-fraud SEO pages sat on the domain in
August 2026. This is the moderation path until an admin surface exists.

Prints each row and writes a JSON backup before deleting anything, so a
mistaken takedown can be restored. Comments cascade with the paste.

    python -m backend.scripts.delete_pastes <slug> [<slug> ...] --backup out.json
"""

import argparse
import asyncio
import json
import sys

from ..database import close_db, get_pool, init_pool

SELECT_SQL = """
    SELECT id, slug, edit_token, title, content_type, content, visibility,
           comments_enabled, view_count, created_at, updated_at
      FROM pastes
     WHERE slug = ANY($1::text[])
"""

DELETE_SQL = "DELETE FROM pastes WHERE slug = ANY($1::text[])"


async def delete_pastes(slugs: list[str], backup_path: str) -> None:
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(SELECT_SQL, slugs)
        found = {r["slug"] for r in rows}
        missing = [s for s in slugs if s not in found]
        if missing:
            raise SystemExit(f"No paste with these slugs: {', '.join(missing)}")

        with open(backup_path, "w") as f:
            json.dump([dict(r) for r in rows], f, indent=2, default=str)
        print(f"Backed up {len(rows)} pastes to {backup_path}\n")

        for r in rows:
            print(f"  {r['slug']}  [{r['visibility']}]  {r['title']}")

        # One statement in a transaction: either every named paste goes or none does.
        async with conn.transaction():
            result = await conn.execute(DELETE_SQL, slugs)
        print(f"\n{result}")

    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete Stash Pages pastes by slug.")
    parser.add_argument("slugs", nargs="+")
    parser.add_argument("--backup", required=True, help="Path to write the JSON backup")
    args = parser.parse_args()
    asyncio.run(delete_pastes(args.slugs, args.backup))


if __name__ == "__main__":
    sys.exit(main())
