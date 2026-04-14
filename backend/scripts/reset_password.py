"""Admin password reset.

Usage:
    python -m backend.scripts.reset_password <username> <new_password>

Reads DATABASE_URL from the environment (or backend/.env) and updates the
user's password_hash in place. No emails, no tokens — this is an admin
escape hatch for when a user forgets their password.
"""

import asyncio
import sys

import asyncpg

from ..auth import hash_password
from ..config import settings


async def reset(username: str, new_password: str) -> int:
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        result = await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE name = $2",
            hash_password(new_password),
            username,
        )
    finally:
        await conn.close()

    # asyncpg returns "UPDATE <rowcount>"
    return int(result.split()[-1])


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python -m backend.scripts.reset_password <username> <new_password>", file=sys.stderr)
        sys.exit(2)

    username, new_password = sys.argv[1], sys.argv[2]
    if len(new_password) < 8:
        print("error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    updated = asyncio.run(reset(username, new_password))
    if updated == 0:
        print(f"error: no user named {username!r}", file=sys.stderr)
        sys.exit(1)

    print(f"password reset for {username}")


if __name__ == "__main__":
    main()
